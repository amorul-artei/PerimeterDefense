# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      19.01.2022 voicua: Created "processVideos.py" to run analysis on a directory

import videoAnalyzeRateOfChange

import ffmpeg

import os
import time
#from os import listdir
#from os.path import isfile, join


def GetFormattedFileSize( size ):
    sizeInGb = float( size ) / (1024.0 * 1024.0 * 1024.0)
    return "{:.2f}GiB".format( sizeInGb )

def GetFormattedFileStats( f ):
    return f[ 0 ] + ', ' + \
        time.strftime( '%Y.%m.%d %H:%M:%S', time.localtime( f[ 1 ] ) ) + ', ' + \
        GetFormattedFileSize( f[ 2 ] )

def WithinRange( v1, v2, r ):
    return abs( v2 - v1 ) <= r

def AnalyzeTimeline( videosList ):
    expectedCreationTime = 0
    for f in videosList:
        # Check if current start time fits expected range
        if expectedCreationTime > 0:
            if not WithinRange( expectedCreationTime, f[ 1 ], 1 ):
                print( f[ 0 ] + " started with delay of " + str( f[ 1 ] - expectedCreationTime ) + " seconds" )
        videoMeta = ffmpeg.probe( f[ 0 ] )[ "streams" ]

        duration = videoMeta[ 0 ][ 'duration' ]
        expectedCreationTime = f[ 1 ] + duration


onlyVideos = [ f for f in os.listdir() if os.path.isfile( f ) and f.lower().endswith( ".mp4" ) ]

alreadyAnalyzedVideos = [ f for f in onlyVideos if "_ROC_analyzed" in f ]
tobeAnalyzedVideos = list( set( onlyVideos ) - set( alreadyAnalyzedVideos ) )

origNames = []
if len( alreadyAnalyzedVideos ) > 0:
    print( "Found previous analysis, skipping" )
    for f in alreadyAnalyzedVideos:
        origName = f[ :f.find( "_ROC_analyzed" ) ]
        print( origName )
        origNames.append( origName )

tobeAnalyzedVideos = list( set( tobeAnalyzedVideos ) - set( origNames ) )
tobeAnalyzedVideos = [ (f, os.path.getmtime( f ), os.path.getsize( f ) ) for f in tobeAnalyzedVideos ]
tobeAnalyzedVideos.sort( key = lambda x: x[ 1 ] )

for f in tobeAnalyzedVideos:
    print( GetFormattedFileStats( f ) )

print( "A total of %i videos to analyze" % len( tobeAnalyzedVideos ) )

#AnalyzeTimeline( tobeAnalyzedVideos )

for a in tobeAnalyzedVideos:
    print( "" )
    print( "" )
    print( "------------------------------------------------------" )
    print( "Running analysis for " + GetFormattedFileStats( a ) )
    videoAnalyzeRateOfChange.runRateOfChangeAnalysis( a[ 0 ] )
    print( "" )


print( "" )
print( "All done." )
