# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      04.02.2022 voicua: Created "videoAnalysisHelpers.py" to contain common constructs.

import os
import time


import tracemalloc
from collections import defaultdict
import gc


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


def FormatMemSize( size ):
    sizeInGb = float( size ) / (1024.0 * 1024.0 * 1024.0)
    return "{:.2f}GiB".format( sizeInGb )

def GetFormattedFileTime( fileTime ):
    return time.strftime( '%Y.%m.%d %H:%M:%S', time.gmtime( fileTime ) )

def GetFormattedFileStats( f ):
    return f[ 0 ] + ', ' + \
        GetFormattedFileTime( f[ 1 ] ) + ', ' + \
        FormatMemSize( f[ 2 ] )


class ObjectsTracker:
    def __init__( self ):
        self.before = None
        self.after = None

    def MakeDictionary():
        objs = defaultdict( int )
        for i in gc.get_objects():
            objs[ type( i ) ] += 1
        return objs

    def StartTracking( self ):
        self.before = ObjectsTracker.MakeDictionary()

    def TakeSnapshot( self ):
        self.after = ObjectsTracker.MakeDictionary()

    def UpdateBaseline( self ):
        if self.after is None:
            self.StartTracking()
        else:
            self.before = self.after

    def PrintStats( self ):
        for k in self.after:
            if self.after[ k ] - self.before[ k ] > 0:
                print( "{0:20}{1:15}".format( str( k ), str( self.after[ k ] - self.before[ k ] ) ) )


def TraceMallocSnapshot():
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')

    print("[ Top 10 allocations ]")
    for stat in top_stats[:10]:
        print(stat)
