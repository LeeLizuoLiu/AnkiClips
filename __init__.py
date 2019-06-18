from .pydub import AudioSegment 
from .pydub.silence import split_on_silence 
import sys
import time
import os
from .aip import AipSpeech
import subprocess
from anki.notes import Note
from aqt import mw
from aqt.utils import getFile, showInfo, showText
from aqt.qt import *
from aqt.profiles import ProfileManager
from collections import namedtuple
from shutil import copy

def audio_segReco(name,sound):
    # Setting specifications 
    silence_thresh=-70 # silent threshold 
    min_silence_len=300 # silence length 
    length_limit=10.33*1000 # The clip length limit after segmentation 
    abandon_chunk_len=100 #  Discard the clips whose length is smaller than abandon_chunk_len ms 
    joint_silence_len=10 # The joint silence length when connect 2 clips 
    
    # Segmentations 
    total = prepare_for_baiduaip(name,sound,silence_thresh\
                                 ,min_silence_len,length_limit,abandon_chunk_len,joint_silence_len)
    client = AipSpeech(APP_ID, API_KEY, SECRET_KEY)
    path = './chunks'
    audiolist = getfilelist(path,pcm=False)
    for file in audiolist:
        audioname = file.split('.')
        subprocess.call(['ffmpeg', '-y', '-i', path+'/'+audioname[0]+'.mp3',\
                         '-acodec', 'pcm_s16le', '-f', 's16le', '-ac', '1', '-ar', "16000", path+'/'+audioname[0]+'.pcm'])
    pcmlist = getfilelist('./chunks',pcm=True)
    text = dict()
    for pcmfile in pcmlist:
        text_temp = client.asr(get_file_content('./chunks/'+pcmfile), 'pcm', 16000, {'dev_pid': 1737,})
        if text_temp["err_no"]==0:
            clip_name = pcmfile.split('.')
            text[clip_name[0]] = text_temp["result"]
        else: 
            raise RuntimeError(text_temp["err_msg"])
    #Delete .pcm file
    for pcmfile in pcmlist:
        os.remove('chunks/'+pcmfile)
    collectionpath = ProfileManager.collectionPath()
    #Copy .mp3 files to collection.media
    for audiofile in audiolist:
        copy('chunks/'+audiofile,collectionpath)
    print("Clips have been copied to collection.media")                
    return text   

def createCards():
    path = getFile(mw, 'Open audio files', cb=None, filter='Audio file (*.mp3,*.wav)', key='Audios')
    if path:
        lower_path = path.lower()
        if lower_path.endswith('mp3'):
            sound = AudioSegment.from_mp3(path) 
        elif lower_path.endswith('wav'):
            sound = AudioSegment.from_wav(path) 
        else:
            raise RuntimeError(f'Unknown audio types in path: {path!r}')
    else:
        raise RuntimeError('No audio selected!')
    text = audio_segReco(path,sound)

    msg = ""
    mw.progress.start(immediate=True)
    msg += buildCard(text) + "\n"
    mw.progress.finish()
    utils.showText(msg)

def buildCard(text):
    config = mw.addonManager.getConfig(__name__)
    if config:
        MODEL = config['model']
        target_fields = config['target_fields']
        Deck = config['Deck']
    else:
        msg = """
        AnkiClips:
        The add-on missed the configuration file.
        If you would not get the right feeds,
        please reinstall this add-on."""
        utils.showWarning(msg)    

    # get deck and model
    deck  = mw.col.decks.get(mw.col.decks.id(Deck))
    model = mw.col.models.byName(MODEL)

    # assign model to deck
    mw.col.decks.select(deck['id'])
    mw.col.decks.get(deck)['mid'] = model['id']
    mw.col.decks.save(deck)

    # assign deck to model
    mw.col.models.setCurrent(model)
    mw.col.models.current()['did'] = deck['id']
    mw.col.models.save(model)

    # iterate notes
    adds = 0
    for key in text.keys():
        note = mw.col.newNote()
        note["audio"] = "[sound:"+key+".mp3]"
        note["text"] = text[key]
        mw.col.addNote(note)
        adds += 1

    mw.col.reset()
    mw.reset()

    # show result
    msg = ngettext("%d note added", "%d notes added", adds) % adds
    msg += "\n"
    return msg

def get_file_content(filePath):
    with open(filePath, 'rb') as fp:
        return fp.read()

    
def getfilelist(path,pcm=True):
    return_list = []
    f_list = os.listdir(path)
    if pcm==True:
        for i in f_list:
            if os.path.splitext(i)[1] == '.pcm':
                return_list.append(i)
    else:
        for i in f_list:
            if os.path.splitext(i)[1] == '.mp3':
                return_list.append(i)        
    return return_list    

def prepare_for_baiduaip(name,sound,silence_thresh=-65,min_silence_len=700,\
                         length_limit=60*1000,abandon_chunk_len=500,joint_silence_len=1300): 
    '''
    Split audio files into sizes that fit Baidu speech recognition
    Baidu currently offers free one-minute-long speech recognition.
    Split the audio by parameters first, and each fragment is disassembled for less than 1 minute.
    Then merge the adjacent segments that are too short, and the merged fragments are still no longer than 1 minute.
    
    Args:
    
        name:                     Audio file name
        sound:                    Audio file data      
        silence-thresh:            default -70 db  # Default silent threshold  
        min-silence-len:           default 700 ms  # Default silence length  
        length-limit:        default 60 x 1000 ms  # The clip length limit after segmentation
        abandon-chunk-len:         default 500 ms  #  Discard the clips whose length is smaller than abandon_chunk_len ms
        joint-silence-len:        default 1300 ms  # The joint silence length when connect 2 clips
    Return: 
        
        total: Number of fragments
    '''  
    print('Start splitting (please be patient if audio is long)\n',' *'*30) 
    chunks = chunk_split_length_limit(sound,min_silence_len=min_silence_len,\
                                      length_limit=length_limit,silence_thresh=silence_thresh)
    #silence time:700ms and silence_dBFS<-70dBFS 
    print('Splitting is finished, return number of segments:',len(chunks),'\n',' *'*30) 
    
    
    # Discard clips that are less than 0.5 seconds
    for i in list(range(len(chunks)))[::-1]: 
        if len(chunks[i])<=abandon_chunk_len: 
            chunks.pop(i) 
    
    # Adjacent segments with short time will be merged, with a merged segment no more than 1 minute 
    chunks = chunk_join_length_limit(chunks,joint_silence_len=joint_silence_len,length_limit=length_limit) 
    
    if not os.path.exists('./chunks'):os.mkdir('./chunks') 
    namef,_ = os.path.splitext(name)
    name_last = namef.split('\\') 
    namec = "mp3" 
    namef = name_last[-1]

    total = len(chunks) 
    for i in range(total): 
        new = chunks[i] 
        save_name = '%s_%04d.%s'%(namef,i,namec) 
        new.export('./chunks/'+save_name, format=namec) 
        print('%04d'%i,len(new))
    print('Clips have already been Saved into dir ./chunks.')
    
    return total

def chunk_split_length_limit(chunk,min_silence_len=700,length_limit=60*1000,silence_thresh=-65,level=0): 

    if len(chunk)>length_limit: # If clips' length is over length-limit, split 
        print('%d Splitting ,len=%d,dBFs=%d'%(level,min_silence_len,silence_thresh)) 
        chunk_splits = split_on_silence(chunk,min_silence_len=min_silence_len,silence_thresh=silence_thresh) 
        
        min_silence_len-=5
        silence_thresh +=1
        if min_silence_len<=0: 
            tempname = 'temp_%d.wav'%int(time.time()) 
            chunk.export(tempname, format='mp3')
            print('%d The parameter has become negative %d,still  %d ms long,and the fragment has been saved to %s'\
                  %(level,min_silence_len,len(chunk),tempname)) 
            raise Exception  
        if len(chunk_splits)<2: 
            # If the split fails, shorten the silence time, nesting chunk_split-length-limit to tear 
            print('%d Split fails, set interval of %d ms, call method continues to split'%(level,min_silence_len)) 
            chunk_splits = chunk_split_length_limit(chunk,min_silence_len=min_silence_len,\
                                                    length_limit=length_limit,silence_thresh=silence_thresh,level=level+1) 
        else:  
            print('%d Split successful, %d segments in total, check the length after split step by segment'\
                  %(level,len(chunk_splits))) 
            arr = []  
            for c in chunk_splits: 
                if len(c)<length_limit: 
                    print('%d The length is smaller than length limit,len=%d'%(level,len(c))) 
                    arr.append(c) 
                else:  
                    print('%d The clip length exceeds the limit length. len=%d,set min_silence_len=%d,Call method continues to split'\
                          %(level,len(c),min_silence_len)) 
                    arr+=chunk_split_length_limit(c,min_silence_len=min_silence_len,\
                                                  length_limit=length_limit,silence_thresh=silence_thresh,level=level+1) 
            chunk_splits = arr 
    else: 
        chunk_splits=[] 
        chunk_splits.append(chunk) 
    return chunk_splits 

def chunk_join_length_limit(chunks,joint_silence_len=1300,length_limit=60*1000): 
    '''
     Merge sound files and limit the maximum length for a single fragment, returning as a list

     Args:
     
         chunk: audio lists
         joint-silence-len: File interval when merging, default 1.3 seconds.
         length-limit: A single file is no longer than this value after the merge, with default 1 minute.
        
     Return: 
         
         adjust-chunks: a list
    '''  
    silence = AudioSegment.silent(duration=joint_silence_len) 
    adjust_chunks=[] 
    temp = AudioSegment.empty() 
    for chunk in chunks: 
        length = len(temp)+len(silence)+len(chunk)   
        if length<length_limit+5*1000:  
            temp+=silence+chunk 
        else:   
            adjust_chunks.append(temp) 
            temp=chunk 
    adjust_chunks.append(temp) 
    return adjust_chunks


action = QAction('Create audio flashcards...', mw)
action.triggered.connect(createCards)
mw.form.menuTools.addAction(action)
