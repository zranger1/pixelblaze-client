#!/usr/bin/env python3
import argparse, fnmatch, pathlib
# Pixelblaze client library
from pixelblaze import *

# ------------------------------------------------

# Callable function for use with zipfile packaging.
def pbbTool():

    def backupToPBB(ipAddress, fileName):
        print(f"Backing up {ipAddress} to {fileName}")
        # Read a Pixelblaze Binary Backup (PBB) from the Pixelblaze at {ipAddress} and write it to {fileName}.
        PBB.fromIpAddress(ipAddress, proxyUrl=args.proxyUrl, verbose=args.verbose).toFile(fileName, args.explode)

    def restoreFromPBB(ipAddress, fileName):
        print(f"Restoring {ipAddress} from {fileName}")
        # Read a Pixelblaze Binary Backup (PBB) from {fileName} and write it to the Pixelblaze at {ipAddress}.
        PBB.fromFile(fileName).toIpAddress(ipAddress, proxyUrl=args.proxyUrl, verbose=args.verbose)

    def cloneFromPBB(ipAddress, fileName):
        print(f"Cloning {ipAddress} from {fileName}")
        # Read a Pixelblaze Binary Backup (PBB) from {fileName} and write only the patterns to the Pixelblaze at {ipAddress}.
        pbb = PBB.fromFile(fileName)
        pb = Pixelblaze(ipAddress, proxyUrl=args.proxyUrl)
        # Delete all the patterns that are currently loaded on the Pixelblaze.
        for filename in pb.getFileList(PBB.fileTypes.filePattern | PBB.fileTypes.filePatternSetting):
            if args.verbose: print(f"  Deleting {filename}")
            pb.deleteFile(filename)
        # Upload all the pattern in this PixelBlazeBackup to the Pixelblaze.
        for filename in pbb.getFileList(PBB.fileTypes.filePattern | PBB.fileTypes.filePatternSetting):
            if args.verbose: print(f"  Uploading {filename}")
            pb.putFile(filename, pbb.getFile(filename))

    def listPBB(pbb):
        if args.verbose:
            # List all the files on the filesystem by internal name.
            print(f"The backup of '{pbb.deviceName}' contains the following files:")
            for fileName in pbb.getFileList():
                realName = ""
                if fileName.startswith('/p/'):
                    if fileName.endswith('.c'):
                        realName = f"({PBP.fromBytes(pathlib.Path(fileName[3:]).stem, pbb.getFile(fileName[:-2])).name} controls)"
                    else:
                        realName = f"  ({PBP.fromBytes(pathlib.Path(fileName[3:]).stem, pbb.getFile(fileName)).name})"
                print(f'  {fileName} {realName}')
        else:
            # List the user-friendly Pattern names.
            print(f"The backup of '{pbb.deviceName}' contains the following patterns:")
            patterns = []
            # Only list the friendly names of the pattern files.
            for fileName in pbb.getFileList(PBB.fileTypes.filePattern):
                pbp = PBP.fromBytes(pathlib.Path(fileName).stem, pbb.getFile(fileName))
                patterns.append((fileName, pbp.name))

            # Sort the pattern list by name because the it was originally sorted by ID.
            patterns.sort(key=lambda tup: str.lower(tup[1]))
            for patternName in patterns:
                print(f'  {patternName[1]}')

    def extractFromPBB(pbbFile, patternName):
        print(f"Extracting patterns matching '{patternName} from '{pbbFile}':")
        # Read a Pixelblaze Binary Backup (PBB) from {fileName} and write only the patterns to the Pixelblaze at {ipAddress}.
        pbb = PBB.fromFile(pbbFile)
        # Go through the list of patterns stored in the Pixelblaze Binary Backup...
        for fileName in pbb.getFileList(PBB.fileTypes.filePattern):
            # ...convert them into Pixeblaze Binary Pattern objects...
            pbp = PBP.fromBytes(pathlib.Path(fileName).stem, pbb.getFile(fileName))
            if fnmatch.fnmatch(pbp.name, patternName):
                # ...and export any with matching patternNames as files.
                print(f'  {pbp.name}')
                pbp.toEPE().toFile(pathlib.Path(pbbFile).with_name(pbp.name).with_suffix('.epe'))

# ------------------------------------------------

    # Create the top-level parser.
    parser = argparse.ArgumentParser(prog='pbbTool')
    # Create separate subparsers for the commands.
    subparsers = parser.add_subparsers(required=True, dest='command')
    # Create the subparser for the "backup" command.
    parserBackup = subparsers.add_parser('backup', help='backup --ipAddress=* --pbbFile=*')
    parserBackup.add_argument("--ipAddress", default='*', help="The (wildcard-enabled) IP address of the Pixelblaze to backup FROM; defaults to '*'")
    parserBackup.add_argument("--pbbFile", default='*', help="The (wildcard-enabled) filename of the PixelBlazeBackup (PBB) file to backup TO; defaults to './*'")
    parserBackup.add_argument("--explode", action='store_true', help="Explode the backup file into its components")
    parserBackup.add_argument("--verbose", action='store_true', help="Display debugging output")
    parserBackup.set_defaults(func=backupToPBB)
    # Create the subparser for the "restore" command.
    parserRestore = subparsers.add_parser('restore', help='restore --ipAddress={ipAddress} --pbbFile={pbbFile.pbb}')
    parserRestore.add_argument("--pbbFile", required=True, help="The filename of the PixelBlazeBackup (PBB) file to restore FROM")
    parserRestore.add_argument("--ipAddress", required=True, help="The IP address of the Pixelblaze to restore TO")
    parserRestore.add_argument("--verbose", action='store_true', help="Display debugging output")
    parserRestore.set_defaults(func=restoreFromPBB)
    # Create the subparser for the "clone" command.
    parserClone = subparsers.add_parser('clone', help='clone --fromAddress={ipAddress} --toAddress={ipAddress}')
    parserClone.add_argument("--pbbFile", required=True, help="The filename of the PixelBlazeBackup (PBB) file to clone FROM")
    parserClone.add_argument("--ipAddress", required=True, help="The IP address of the Pixelblaze to clone TO")
    parserClone.add_argument("--verbose", action='store_true', help="Display debugging output")
    parserClone.set_defaults(func=cloneFromPBB)
    # Create the subparser for the "list" command.
    parserList = subparsers.add_parser('list', help='list --ipAddress=* OR --pbbFile=*')
    listGroup = parserList.add_mutually_exclusive_group(required=True)
    listGroup.add_argument("--pbbFile", help="The filename of the PixelBlazeBackup (PBB) file to list")
    listGroup.add_argument("--ipAddress", default='*', help="The (wildcard-enabled) IP address of the Pixelblaze to list")
    parserList.add_argument("--verbose", action='store_true', help="Display debugging output")
    parserList.set_defaults(func=listPBB)
    # Create the subparser for the "extract" command.
    parserExtract = subparsers.add_parser('extract', help='extract --pbbFile={pbbFile.pbb} --patternName=*')
    parserExtract.add_argument("--pbbFile", required=True, help="The filename of the PixelBlazeBackup (PBB) file to extract")
    parserExtract.add_argument("--patternName", required=True, default='*', help="The (wildcard-enabled) name of the pattern(s) to extract")
    parserExtract.add_argument("--verbose", action='store_true', help="Display debugging output")
    parserExtract.set_defaults(func=extractFromPBB)
    # Add common arguments.
    parser.add_argument("--proxyUrl", default=None, help="Redirect Pixelblaze traffic through a proxy at 'protocol://address:port'")

    # Parse the command line.
    args = parser.parse_args()

    if args.command in ['backup']:
        # Enumerate the available Pixelblazes on the network and see which ones match.
        for ipAddress in Pixelblaze.EnumerateAddresses(timeout=1500):
            if (fnmatch.fnmatch(ipAddress, args.ipAddress)):
                with Pixelblaze(ipAddress, proxyUrl=args.proxyUrl) as pixelblaze:
                    # Substitute in the correct device name for any wildcards in the filename.
                    fileName = pathlib.Path(args.pbbFile.replace('*', pixelblaze.getDeviceName())).with_suffix('.pbb')
                    # Call the appropriate routine to backup.
                    args.func(pixelblaze.ipAddress, fileName)

    elif args.command in ['restore', 'clone']:
        # No wildcarding here; because of the potential data loss everything must be specified explicitly.
        # Call the appropriate routine to restore or clone from backup.
        args.func(args.ipAddress, args.pbbFile)

    elif args.command in ['extract']:
        # Call the appropriate routine to export a pattern from the backup.
        args.func(args.pbbFile, args.patternName)

    elif args.command in ['list']:
        if args.pbbFile is not None:
            for fileName in pathlib.Path().glob(args.pbbFile):
                args.func(PBB.fromFile(fileName))
        elif args.ipAddress is not None:
            # Enumerate the available Pixelblazes on the network and see which ones match.
            for ipAddress in Pixelblaze.EnumerateAddresses(timeout=1500):
                if (fnmatch.fnmatch(ipAddress, args.ipAddress)):
                    args.func(PBB.fromIpAddress(ipAddress, args.verbose))
        else:
            parser.print_usage()

# ------------------------------------------------

# Main routine for invoking directly.
if __name__ == "__main__":
    pbbTool()
    exit()

