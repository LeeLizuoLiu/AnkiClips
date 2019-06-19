__window = None

import sys, math, time

from anki.notes import Note
from aqt import mw
from aqt.utils import getFile, showInfo, showText
from aqt.qt import *
from . import utils

class AnkiClipsWindow(QWidget):
    
    # main window of AnkiClips plugin
    def __init__(self):
        super(AnkiClipsWindow, self).__init__()

        self.results = None
        self.thread = None

        self.initGUI()

    # create GUI skeleton
    def initGUI(self):
        
        self.box_top = QVBoxLayout()
        self.box_upper = QHBoxLayout()

        # left side
        self.box_left = QVBoxLayout()

        # quizlet url field
        self.box_name = QHBoxLayout()
        self.label_url = QLabel("Audio path:")
        self.text_url = QLineEdit("",self)
        self.text_url.setMinimumWidth(300)

        self.box_name.addWidget(self.label_url)
        self.box_name.addWidget(self.text_url)

        # add layouts to left
        self.box_left.addLayout(self.box_name)

        # right side
        self.box_right = QVBoxLayout()

        # code (import set) button
        self.box_code = QVBoxLayout()
        self.button_code_1 = QPushButton("Browse...", self)
        self.box_code.addStretch(1)
        self.box_code.addWidget(self.button_code_1)
        self.button_code_1.clicked.connect(self.selectFile)
        self.button_code_2 = QPushButton("Create...", self)
        self.box_code.addStretch(2)
        self.box_code.addWidget(self.button_code_2)
        self.button_code_2.clicked.connect(self.onCode)
        # add layouts to right
        self.box_right.addLayout(self.box_code)

        # add left and right layouts to upper
        self.box_upper.addLayout(self.box_left)
        self.box_upper.addSpacing(20)
        self.box_upper.addLayout(self.box_right)

        # results label
        self.label_results = QLabel("")

        # add all widgets to top layout
        self.box_top.addLayout(self.box_upper)
        self.box_top.addWidget(self.label_results)
        self.box_top.addStretch(1)
        self.setLayout(self.box_top)

        # go, baby go!
        self.setMinimumWidth(500)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.setWindowTitle("Anki audio flashcards importer")
        self.show()

    def selectFile(self):
        self.path = getFile(mw, 'Open audio files', cb=None, filter="*.mp3", key='Audios')
        self.text_url.setText(self.path)

    def onCode(self):

        if not self.thread == None:
            self.thread.terminate()

        self.label_results.setText("Segmenting and recognizing, please wait...")
        self.thread = Audioseperator(self, self.path)
        self.thread.start()

        while not self.thread.isFinished():
            mw.app.processEvents()
            self.thread.wait(50)

        msg = ""
        mw.progress.start(immediate=True)
        msg += self.buildCard(self.thread.text) + "\n"
        mw.progress.finish()
        self.label_results.setText(msg)

        self.thread.terminate()
        self.thread = None

    def buildCard(self,text):
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



class Audioseperator(QThread):
    def __init__(self, window, path):
        super(Audioseperator, self).__init__()
        self.window = window

        self.path = path
        self.text = None

    def run(self):
        self.text = self.audio_segReco(self.path)

    def audio_segReco(self,name):
        # Setting specifications 
        silence_thresh=-70 # silent threshold 
        min_silence_len=300 # silence length 
        length_limit=10.33*1000 # The clip length limit after segmentation 
        abandon_chunk_len=100 #  Discard the clips whose length is smaller than abandon_chunk_len ms 
        joint_silence_len=10 # The joint silence length when connect 2 clips 
        
        # Segmentations 
        total = utils.prepare_for_baiduaip(name,silence_thresh\
                                    ,min_silence_len,length_limit,abandon_chunk_len,joint_silence_len)

        APP_ID = '16105503'
        API_KEY = 'ot75P7iKUGCzPxKyhVi4ZQTm'
        SECRET_KEY = 'S2oPnF04fw5abAlB6SNHc8XgGDhoEQD1'

        client = utils.AipSpeech(APP_ID, API_KEY, SECRET_KEY)
        path = './chunks'
        audiolist = utils.getfilelist(path,pcm=False)
        for file in audiolist:
            audioname = file.split('.')
            utils.subprocess.call(['ffmpeg', '-y', '-i', path+'/'+audioname[0]+'.mp3',\
                            '-acodec', 'pcm_s16le', '-f', 's16le', '-ac', '1', '-ar', "16000", path+'/'+audioname[0]+'.pcm'])
        pcmlist = utils.getfilelist('./chunks',pcm=True)
        text = dict()
        for pcmfile in pcmlist:
            text_temp = client.asr(utils.get_file_content('./chunks/'+pcmfile), 'pcm', 16000, {'dev_pid': 1737,})
            if text_temp["err_no"]==0:
                clip_name = pcmfile.split('.')
                text[clip_name[0]] = text_temp["result"][0]
            else: 
                raise RuntimeError(text_temp["err_msg"])
        #Delete .pcm file
        for pcmfile in pcmlist:
            utils.os.remove('chunks/'+pcmfile)
        collectionpath = mw.pm.collectionPath()
        collectionpath = collectionpath.replace('\\','/')
        collectionpath = collectionpath.replace('anki2','media')
        #Copy .mp3 files to collection.media
        for audiofile in audiolist:
            utils.copy('chunks/'+audiofile,collectionpath)
            utils.os.remove('chunks/'+audiofile)
        #print("Clips have been copied to collection.media")                
        return text   



def runAnkiClipsPlugin():
    global __window
    __window = AnkiClipsWindow()
