#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      19.01.2022 voicua: Created "processVideos.py" to run analysis on a directory

import os, sys
import tempfile
import shutil
from time import perf_counter
import argparse, shlex

import ffmpeg

import audioAnalyze
import videoAnalyzeRateOfChange
import videoAnalysisHelpers as vh

kTempLogFilePrefix = "temp_logfile_"


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


def CleanupPreviousRun( destFolder ):
    filesToRemove = [ f for f in os.listdir( destFolder ) if os.path.isfile( os.path.join( destFolder, f ) ) and \
        ( f.lower().startswith( videoAnalyzeRateOfChange.kTempFilePrefix.lower() ) or \
          f.lower().startswith( kTempLogFilePrefix.lower() ) ) ]
    print( "Removing %i temporary files from previous run..." % len( filesToRemove ) )
    for f in filesToRemove:
        os.remove( os.path.join( destFolder, f ) )


def DoGoProSpecificCleanup():
    # Remove all *lrv and *thm files
    filesToRemove = [ f for f in os.listdir() if os.path.isfile( f ) and \
        ( f.lower().endswith( ".lrv" ) or f.lower().endswith( ".thm" ) ) ]
    print( "Removing %i GoPro low resolution videos..." % len( filesToRemove ) )
    for f in filesToRemove:
        os.remove( f )

    # Rename all *.360 to *.360.mp4
    filesToRename = [ f for f in os.listdir() if os.path.isfile( f ) and f.lower().endswith( ".360" ) ]
    print( "Renaming %i 360 GoPro videos so that imageio accepts them..." % len( filesToRename ) )
    for f in filesToRename:
        os.rename( f, f + ".mp4" )

def DoGarminSpecificCleanup():
    # Remove all *.glv
    filesToRemove = [ f for f in os.listdir() if os.path.isfile( f ) and f.lower().endswith( ".glv" ) ]
    print( "Removing %i Garmin low resolution videos..." % len( filesToRemove ) )
    for f in filesToRemove:
        os.remove( f )


def IsVideoFile( fileName ):
    return os.path.isfile( fileName ) and \
        (fileName.lower().endswith( ".mp4" ) or fileName.lower().endswith( ".avi" ))

def IsVideoFileWithName( destFolder, fileName, withNameDecorator = None ):
    return os.path.isfile( os.path.join( args.destFolder, fileName ) ) and \
        (fileName.lower().endswith( ".mp4" ) or fileName.lower().endswith( ".avi" )) and \
        ( withNameDecorator is None or withNameDecorator in fileName )


# if processing anything in batch, only commit the move operation
# when the output has been properly saved to disk.
class DelayedMoveOperation:
    def __init__( self, targetPath ):
        self.targetPath = targetPath
        self.filePaths = []

    def Cancel( self ):
        self.filePaths.clear()

    def AddFile( self, filePath ):
        self.filePaths.append( filePath )

    def GetCount( self ):
        return len( self.filePaths )

    def Commit( self ):
        if not os.path.exists( self.targetPath ):
            os.mkdir( self.targetPath )
        for f in self.filePaths:
            shutil.move( f, os.path.join( self.targetPath, f ) )
        self.filePaths.clear()


def runProcessVideos( args ):

    #
    # Prepare the folder for a new analysis, by doing some initial maintenance
    #

    if not os.path.exists( args.destFolder ):
        os.makedirs( args.destFolder )
        
    jobLogger = vh.Logger( os.path.join( args.destFolder, "processVideosLog.txt" ) )

    CleanupPreviousRun( args.destFolder )
    DoGoProSpecificCleanup()
    DoGarminSpecificCleanup()

    #
    # Calculate the list of videos that must be processed. Remove from the list any videos already analyzed.
    # This in turn enables the user to restart the process on a previously interrupted run.
    #

    allSourceVideos = [ f for f in os.listdir() if IsVideoFile( f ) ]

    rocPreviousResults = [ f for f in os.listdir( args.destFolder ) if IsVideoFileWithName( args.destFolder, f, "_ROC_analyzed" ) ]
    # initialize the list with all the originals found in the folder
    tobeAnalyzedVideos = list( set( allSourceVideos ) - set( rocPreviousResults ) )

    alreadyAnalyzedOriginals = []

    '''
    # TODO-Pri3: figure out if I still need this feature.
    # For now, analyzed/aborted videos are moved to a different path, with cancel semantics
    allTextFiles = [ f for f in os.listdir( args.destFolder ) \
        if os.path.isfile( os.path.join( args.destFolder, f ) ) and f.lower().endswith( ".txt" ) ]
    for f in allTextFiles:
        origName = os.path.splitext( os.path.basename( f ) )[ 0 ]
        if origName in tobeAnalyzedVideos:
            alreadyAnalyzedOriginals.append( origName )
    '''

    # Remove originals with existing results, even if incomplete analysis, to avoid stealth overwriting of the results
    # Previous results must be explicitly removed by the user
    for f in rocPreviousResults:
        origName = f[ :f.find( "_ROC_analyzed" ) ]
        alreadyAnalyzedOriginals.append( origName )

    alreadyAnalyzedOriginals = set( alreadyAnalyzedOriginals )

    if len( alreadyAnalyzedOriginals ) > 0:
        print( "Found previous analysis, skipping the following %i originals:" % len( alreadyAnalyzedOriginals ) )
        for f in alreadyAnalyzedOriginals:
            jobLogger.PrintMessage( f )


    tobeAnalyzedVideos = list( set( tobeAnalyzedVideos ) - alreadyAnalyzedOriginals )

    #
    # Add aditional file information to the final list, and sort it
    #

    tobeAnalyzedVideos = [ (f, os.path.getmtime( f ), os.path.getsize( f ) ) for f in tobeAnalyzedVideos ]
    tobeAnalyzedVideos.sort( key = lambda x: x[ 1 ] )

    print( "" )
    jobLogger.PrintMessage( "The following video files will be analyzed:" )

    i = 0
    jobSizeBytes = 0
    for f in tobeAnalyzedVideos:
        printToConsole = len( tobeAnalyzedVideos ) <= 10 or ( i in (0, 1, len( tobeAnalyzedVideos ) - 1 ) )
        jobLogger.PrintMessage( vh.GetFormattedFileStats( f ), printToConsole )
        if not printToConsole and i == 2:
            print( "..." )

        jobSizeBytes += f[ 2 ]
        i += 1

    jobLogger.PrintMessage( "A total of %i videos to analyze, %s" % \
        (len( tobeAnalyzedVideos ), vh.FormatMemSize( jobSizeBytes )) )

    #AnalyzeTimeline( tobeAnalyzedVideos )

    #
    # Run analysis
    #

    diskReadingAccumulator = videoAnalyzeRateOfChange.RunningTimeAccumulator()
    jobStartTime = perf_counter()
    totalSourceProcessed = 0

    moveToAnalyzed = DelayedMoveOperation( "AnalyzedVideos" )
    moveToAborted = DelayedMoveOperation( "AbortedVideos" )
    memoryCopy = None

    # initialize analyzer
    count = 1
    rateOfChangeAnalyzer = None

    for a in tobeAnalyzedVideos:
        try:
            print( "" )
            print( "" )
            print( "------------------------------------------------------" )
            print( "-----------------------%i/%i--------------------------" % (count, len( tobeAnalyzedVideos )) )

            tempLoggingFilePath = os.path.join( args.destFolder, kTempLogFilePrefix + a[ 0 ] + ".txt" )
            logger = vh.Logger( tempLoggingFilePath )
            logger.PrintMessage( "Running analysis for " + vh.GetFormattedFileStats( a ) )
            jobLogger.PrintMessage( "Running analysis for " + vh.GetFormattedFileStats( a ), False )

            algPerformanceResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()

            #
            # Copy file to memory, to avoid reading multiple times from potentially slow media
            #

            jobLogger.PrintMessage( "Copying video file to memory..." )
            diskReadingAccumulator.OnStartTimer( a[ 2 ] )
            memoryCopy = tempfile.NamedTemporaryFile( suffix = '.' + os.path.splitext( a[ 0 ] )[1], delete = False )
            shutil.copy( a[ 0 ], memoryCopy.name )
            diskReadingAccumulator.OnStopTimer()
            jobLogger.PrintMessage( "Done copying, at %s." % diskReadingAccumulator.FormatAsMiBPerf( True ) )
            jobLogger.PrintMessage( memoryCopy.name )

            #
            # audio analysis
            #

            audioAnalyze.runAudioAnalysis( memoryCopy.name, vh.GetFormattedFileTime( a[ 1 ] ), logger, args )

            #
            # rate of change analysis
            #

            if rateOfChangeAnalyzer is None:
                sessionName = "Analysis " + vh.GetFormattedFileTime( a[ 1 ] )
                saveTimerStart = perf_counter()
                rateOfChangeAnalyzer = videoAnalyzeRateOfChange.RateOfChangeAnalyzer( args, sessionName )

            rateOfChangeAnalyzer.AddVideoFileToAnalysis( memoryCopy.name, logger, algPerformanceResults )

            if algPerformanceResults.analysisAborted:
                moveToAborted.AddFile( a[ 0 ] )
            else:
                moveToAnalyzed.AddFile( a[ 0 ] )

            # All phases done with current file
            logger.Close()
            os.rename( tempLoggingFilePath, os.path.join( args.destFolder, a[ 0 ] + ".txt" ) )

            #
            # Session(time segment) management and cleanup
            #

            if perf_counter() - saveTimerStart > 10 * 60 or \
                    algPerformanceResults.analysisAborted or rateOfChangeAnalyzer.GetOutputLength() > 5 * 60:
                
                if moveToAnalyzed.GetCount() == 0:
                    # No need to keep output, all files were aborted
                    rateOfChangeAnalyzer.RemoveOutput()
                else:
                    # Keep output. If last file was aborted, partial analysis may still be in the output. That's ok.
                    rateOfChangeAnalyzer.FinishAnalysis()

                rateOfChangeAnalyzer = None
                moveToAnalyzed.Commit()
                moveToAborted.Commit()
                jobLogger.PrintMessage( "Finalizing current session at %i" % count )


            print( "" )
            count += 1

            #
            # Perf counters
            #

            totalSourceProcessed += a[ 2 ]
            currentTime = perf_counter()
            jobRunningTimePerf = totalSourceProcessed / (1024.0 * 1024.0 * ( currentTime - jobStartTime ) )
            dataReadPerf = totalSourceProcessed / (1024.0 * 1024.0 * diskReadingAccumulator.accumulator )

            jobLogger.PrintMessage( "Reading source data at %.2f MiB/s" % dataReadPerf )
            jobLogger.PrintMessage( "Processing source data at a rate of %.2f MiB/s" % jobRunningTimePerf )
            if jobSizeBytes - totalSourceProcessed > 0:
                jobLogger.PrintMessage( "Remaining time to finish: %.2f min" % \
                    float( (( jobSizeBytes - totalSourceProcessed ) / totalSourceProcessed ) * ( currentTime - jobStartTime ) / 60.0) )

        except Exception as e:
            jobLogger.PrintMessage( str( e ) )
            jobLogger.PrintMessage( "Exception thrown during processing, finalizing" )
            break

        finally:
            if not memoryCopy is None:
                memFileName = memoryCopy.name
                memoryCopy.close()
                os.remove( memFileName )



    if not rateOfChangeAnalyzer is None:
        #TODO-Pri0 voicua: add a transaction class with Commit/Cancel semantics
        moveToAnalyzed.Commit()
        moveToAborted.Commit()
        rateOfChangeAnalyzer.FinishAnalysis()

    jobLogger.PrintMessage( "" )
    jobLogger.PrintMessage( "All done." )


if __name__ == "__main__":
    CMDS_FILE_NAME = "cmds.history"
    parser = argparse.ArgumentParser()
    parser.add_argument( "--destFolder", type = str, default = ".",
        help = "optional destination folder for results of analysis. Default: current working directory" )
    parser.add_argument( "--verboseRunningTime", action = "store_true",
        help = "enables display of running time performance split per phases of the algorithm" )
    parser.add_argument( "--cont", action="store_true",
        help="ignores all other parameters and continues previous run from %s file" % CMDS_FILE_NAME )

    args = parser.parse_args()

    # continue previous run?
    if args.cont:
        if not ( os.path.exists( CMDS_FILE_NAME ) and os.path.isfile( CMDS_FILE_NAME ) ):
            print( "File not found: %s" % CMDS_FILE_NAME )
            sys.exit( 1 )
        with open( CMDS_FILE_NAME ) as fp:
            lines = fp.readlines()
            if len( lines ) < 1:
                print( "Empty commands file: %s" % CMDS_FILE_NAME )
                sys.exit( 1 )
            args = parser.parse_args( shlex.split( lines[ -1 ] )[ 1:: ] )
    else:
        # proceed with given arguments
        with open( CMDS_FILE_NAME, "a" ) as fp:
            fp.write( shlex.join( sys.argv ) + '\n' )

    runProcessVideos( args )


#TODO-Pri1 voicua: ability to carbon copy all output to a log file as well
#TODO-Pri0 voicua: unittesting for this file
#TODO-Pri0 voicua: email notifications
#TODO-Pri2 voicua: adaptive sampling rate: categorize videos, assign optimal speeds to those categories, 
#   challenge the speeds by going slower on purpose, to see if movements are missed.
#TODO-Pri0 voicua: save all videos with lower resolution, dropped frame rate, reencoded for compression
#TODO-Pri0 voicua: overall performance metrics, measured in raw source bytes per second processed.
#TODO-Pri0 voicua: copy  source file to memory and do all read operations from there, to read only once (4GB files, etc)
#TODO-Pri2 voicua: overflow folder for disk full
#TODO-Pri0 voicua: I just realized that LRV videos (GoPro has them) might be good enough for the initial ROC analysis, and use the highres 
#   only for subsequent analysis phases. For this I probably should introduce the concept of "original assets" and 
#   "derived assets" to be able to manage multiple files for the same original timeline


