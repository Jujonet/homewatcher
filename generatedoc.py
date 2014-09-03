#!/usr/bin/python3
import argparse
import re

def readIncludedFileLine(filename):
    with open(filename) as file:
        return ''.join(file.readlines())

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('template', help='Template file that contains the markdown to be modified to include the configuration.', metavar='TMP')
    parser.add_argument('output', help='Output file that is the result of the insertion of the configuration sample into the template.')
    args = parser.parse_args()

    inclusionRegex = re.compile('{{.*}}')

    with open(args.template) as templateFile:
        templateLines = templateFile.readlines()
        with open(args.output, 'w') as outputFile:
            for line in templateLines:
                for matchedString in inclusionRegex.findall(line):
                    includeFilename = matchedString[2:-2]
                    line = line.replace(matchedString, readIncludedFileLine(includeFilename), 1)

                outputFile.write(line)
