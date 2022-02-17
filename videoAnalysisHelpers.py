# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      04.02.2022 voicua: Created "videoAnalysisHelpers.py" to contain common constructs.

import os

class Logger:
    def __init__( self, logFileName = None ):
        self.fileHandle = None
        if not logFileName is None:
            self.fileHandle = open( logFileName, 'a' )

    def PrintMessage( self, msg = None, printToConsole = True ):
        if msg is None:
            msg = ""
        if printToConsole:
            print( msg )
        if not self.fileHandle is None:
            self.fileHandle.write( msg + os.linesep )

    def Close( self ):
        self.fileHandle.close()
