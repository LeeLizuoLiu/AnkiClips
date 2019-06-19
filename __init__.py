from .Clips import runAnkiClipsPlugin
from aqt import mw
from aqt.qt import *


def main():
    action = QAction('Create audio flashcards...', mw)
    action.triggered.connect(runAnkiClipsPlugin)
    mw.form.menuTools.addAction(action)

main()