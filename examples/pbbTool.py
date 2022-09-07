#!/usr/bin/env python3
import argparse, fnmatch, pathlib
# Pixelblaze client library
from pixelblaze import *

# ------------------------------------------------

# Callable function for use with zipfile packaging.
def pbbTool():

    def backupPBB(ipAddress, fileName):
        print(f"Backing up {ipAddress} to {fileName}")
        PBB.fromIpAddress(ipAddress, verbose=args.verbose).toFile(fileName, args.explode)

    def restorePBB(ipAddress, fileName):
        print(f"Restoring {ipAddress} from {fileName}")
        PBB.fromFile(fileName).toIpAddress(ipAddress, verbose=args.verbose)

    def listPBB(pbb):
        if args.verbose:
            print(f"The backup of '{pbb.deviceName}' contains the following files:")
            for fileName in pbb.contents:
                realName = ""
                if fileName.startswith('/p/'):
                    if fileName.endswith('.c'):
                        realName = f"({PBP.fromBytes(pathlib.Path(fileName[3:]).stem, pbb.getFile(fileName[:-2])).name} controls)"
                    else:
                        realName = f"  ({PBP.fromBytes(pathlib.Path(fileName[3:]).stem, pbb.getFile(fileName)).name})"
                print(f'  {fileName} {realName}')
        else:
            print(f"The backup of '{pbb.deviceName}' contains the following patterns:")
            patterns = []
            for fileName in pbb.contents:
                if fileName.startswith('/p/'):
                    if not fileName.endswith('.c'):
                        pbp = PBP.fromBytes(pathlib.Path(fileName).stem, pbb.getFile(fileName))
                        patterns.append((fileName, pbp.name))
            patterns.sort(key=lambda tup: str.lower(tup[1]))
            for patternName in patterns:
                print(f'  {patternName[1]}')

# ------------------------------------------------

    # Create the top-level parser.
    parser = argparse.ArgumentParser(prog='pbbTool')
    # Create separate subparsers for the commands.
    subparsers = parser.add_subparsers(required=True, dest='command')
    # Create the subparser for the "backup" command.
    parserBackup = subparsers.add_parser('backup', help='backup --ipAddress=* --pbbFile=*')
    parserBackup.add_argument("--ipAddress", default='*', help="The (wildcard-enabled) IP address of the Pixelblaze to backup; defaults to '*'")
    parserBackup.add_argument("--pbbFile", default='*', help="The (wildcard-enabled) filename of the PixelBlazeBackup (PBB) file; defaults to './*'")
    parserBackup.add_argument("--explode", action='store_true', help="Explode the backup file into its components")
    parserBackup.add_argument("--verbose", action='store_true', help="Display debugging output")
    parserBackup.set_defaults(func=backupPBB)
    # Create the subparser for the "restore" command.
    parserRestore = subparsers.add_parser('restore', help='restore --ipAddress={ipAddress} --pbbFile={pbbFile.pbb}')
    parserRestore.add_argument("--pbbFile", required=True, help="The filename of the PixelBlazeBackup (PBB) file")
    parserRestore.add_argument("--ipAddress", required=True, help="The IP address of the Pixelblaze to to restore")
    parserRestore.add_argument("--verbose", action='store_true', help="Display debugging output")
    parserRestore.set_defaults(func=restorePBB)
    # Create the subparser for the "list" command.
    parserList = subparsers.add_parser('list', help='list --ipAddress=* OR --pbbFile=*')
    listGroup = parserList.add_mutually_exclusive_group(required=True)
    listGroup.add_argument("--pbbFile", help="The filename of the PixelBlazeBackup (PBB) file to list")
    listGroup.add_argument("--ipAddress", default='*', help="The (wildcard-enabled) IP address of the Pixelblaze to list")
    parserList.add_argument("--verbose", action='store_true', help="Display debugging output")
    parserList.set_defaults(func=listPBB)
    # Add common arguments.
    # Parse the command line.
    args = parser.parse_args()


    if args.command in ['backup']:
        # Enumerate the available Pixelblazes on the network and see which ones match.
        for ipAddress in Pixelblaze.EnumerateAddresses(timeout=1500):
            if (fnmatch.fnmatch(ipAddress, args.ipAddress)):
                with Pixelblaze(ipAddress) as pixelblaze:
                    # Substitute in the correct device name for any wildcards in the filename.
                    fileName = pathlib.Path(args.pbbFile.replace('*', pixelblaze.getDeviceName())).with_suffix('.pbb')
                    # Call the appropriate routine to backup.
                    args.func(pixelblaze.ipAddress, fileName)

    elif args.command in ['restore']:
        # No wildcarding here; because of the potential data loss everything must be specified explicitly.
        # Call the appropriate routine to restore.
        args.func(args.ipAddress, args.pbbFile)

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

