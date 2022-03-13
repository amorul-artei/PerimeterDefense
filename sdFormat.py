#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      22.02.2022 voicua: Created "sdFormat.py" to format sd cards.

import sys

import re
import psutil

import subprocess

def ReadUserInput( prompt, validChars ):
    answer = ""
    while not( len( answer ) == 1 and answer in validChars ):
        answer = input( prompt )
    return answer

def GetFormattedFileSize( size ):
    sizeInGb = float( size ) / (1024.0 * 1024.0 * 1024.0)
    return "{:.2f}GiB".format( sizeInGb )


def GetAllowedPartitions():
    partitions = psutil.disk_partitions()
    protectedMountPoints = [ '^/$', '^/boot', '^/media/veracrypt' ]
    selectedList = []
    for p in partitions:
        protected = False
        for pmp in protectedMountPoints:
            x = re.search( pmp, p.mountpoint )
            if not x is None:
                protected = True
                break
        if not protected:
            selectedList.append( p )

    return selectedList


TABLE_TEMPLATE = "{0:15}{1:15}{2:10}{3:15}"

def PrintPartition( p ):
    usage = psutil.disk_usage( p.mountpoint )
    print( TABLE_TEMPLATE.format( \
        p.device, \
        str( GetFormattedFileSize( usage.total ) ), \
        str( usage.percent ), \
        p.mountpoint \
        ) )

def PrintPartitions( partitions ):
    print( TABLE_TEMPLATE.format( "Device", "Size", "Use%", "Mounted on" ) )
    for p in partitions:
        PrintPartition( p )


if __name__ == "__main__":
    allowedPartitions = GetAllowedPartitions()

    if len( sys.argv ) < 2:
        print( "sdFormat.py <partition> [volume label]" )
        print( "    <partition> = device name or mount point. Example: 'sde1' or 'YAHWEH'" )
        print()

        PrintPartitions( allowedPartitions )
        exit( 0 )

    # Search for the partition
    partName = sys.argv[ 1 ]
    target = None
    for p in allowedPartitions:
        if partName in p.device or partName.lower() in p.mountpoint.lower():
            print( "Found partition:" )
            PrintPartitions( [ p ] )
            target = p
            break

    if target is None:
        print( "Specified partition not found" )
        sys.exit( 1 )

    if len( sys.argv ) > 2:
        label = sys.argv[ 2 ]
    else:
        label = p.mountpoint.split( '/' )[ -1 ]
    answer = ReadUserInput( "Proceed with formatting (LABEL = '%s')? (y/n): " % label, "yn" )
    if answer == 'n':
        sys.exit( 0 )

    process = subprocess.run( [ "umount", p.device ] )
    if process.returncode != 0:
        print( "Error dismounting device" )
        sys.exit( process.returncode )

    process = subprocess.run( [ "mkfs.vfat", "-n", label, p.device ] )