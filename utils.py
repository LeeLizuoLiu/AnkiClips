from .pydub import AudioSegment 
from .pydub.silence import split_on_silence 
import sys
import time
import os
from .aip import AipSpeech
import subprocess
from shutil import copy

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


def prepare_for_baiduaip(name,silence_thresh=-65,min_silence_len=700,\
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
    if name:
        lower_path = name.lower()
        if lower_path.endswith('mp3'):
            sound = AudioSegment.from_mp3(name) 
        else:
            raise RuntimeError(f'Unknown audio types in path: {name!r}')
    else:
        raise RuntimeError('No audio selected!')

    #print('Start splitting (please be patient if audio is long)\n',' *'*30) 
    chunks = chunk_split_length_limit(sound,min_silence_len=min_silence_len,\
                                      length_limit=length_limit,silence_thresh=silence_thresh)
    #silence time:700ms and silence_dBFS<-70dBFS 
    #print('Splitting is finished, return number of segments:',len(chunks),'\n',' *'*30) 
    
    
    # Discard clips that are less than 0.5 seconds
    for i in list(range(len(chunks)))[::-1]: 
        if len(chunks[i])<=abandon_chunk_len: 
            chunks.pop(i) 
    
    # Adjacent segments with short time will be merged, with a merged segment no more than 1 minute 
    chunks = chunk_join_length_limit(chunks,joint_silence_len=joint_silence_len,length_limit=length_limit) 
    
    if not os.path.exists('./chunks'):os.mkdir('./chunks') 
    namef,_ = os.path.splitext(name)
    name_last = namef.split('/') 
    namec = "mp3" 
    namef = name_last[-1]

    total = len(chunks) 
    for i in range(total): 
        new = chunks[i] 
        save_name = '%s_%04d.%s'%(namef,i,namec) 
        new.export('./chunks/'+save_name, format=namec) 
        #print('%04d'%i,len(new))
    #print('Clips have already been Saved into dir ./chunks.')
    
    return total

def chunk_split_length_limit(chunk,min_silence_len=700,length_limit=60*1000,silence_thresh=-65,level=0): 

    if len(chunk)>length_limit: # If clips' length is over length-limit, split 
        #print('%d Splitting ,len=%d,dBFs=%d'%(level,min_silence_len,silence_thresh)) 
        chunk_splits = split_on_silence(chunk,min_silence_len=min_silence_len,silence_thresh=silence_thresh) 
        
        min_silence_len-=5
        silence_thresh +=1
        if min_silence_len<=0: 
            tempname = 'temp_%d.mp3'%int(time.time()) 
            chunk.export(tempname, format='mp3')
            #print('%d The parameter has become negative %d,still  %d ms long,and the fragment has been saved to %s'%(level,min_silence_len,len(chunk),tempname)) 
            raise RuntimeError("The clips" + tempname + "can not be segmented!")  
        if len(chunk_splits)<2: 
            # If the split fails, shorten the silence time, nesting chunk_split-length-limit to tear 
            #print('%d Split fails, set interval of %d ms, call method continues to split'%(level,min_silence_len)) 
            chunk_splits = chunk_split_length_limit(chunk,min_silence_len=min_silence_len,\
                                                    length_limit=length_limit,silence_thresh=silence_thresh,level=level+1) 
        else:  
            #print('%d Split successful, %d segments in total, check the length after split step by segment'\%(level,len(chunk_splits))) 
            arr = []  
            for c in chunk_splits: 
                if len(c)<length_limit: 
                   # print('%d The length is smaller than length limit,len=%d'%(level,len(c))) 
                    arr.append(c) 
                else:  
                    #print('%d The clip length exceeds the limit length. len=%d,set min_silence_len=%d,Call method continues to split'\%(level,len(c),min_silence_len)) 
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
