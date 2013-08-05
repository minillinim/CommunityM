#!/usr/bin/env python

###############################################################################
#                                                                             #
#    This program is free software: you can redistribute it and/or modify     #
#    it under the terms of the GNU General Public License as published by     #
#    the Free Software Foundation, either version 3 of the License, or        #
#    (at your option) any later version.                                      #
#                                                                             #
#    This program is distributed in the hope that it will be useful,          #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of           #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            #
#    GNU General Public License for more details.                             #
#                                                                             #
#    You should have received a copy of the GNU General Public License        #
#    along with this program. If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
###############################################################################

"""
Classify 16S fragments by mapping them to the GreenGenes DB with BWA.
"""

__author__ = 'Donovan Parks'
__copyright__ = 'Copyright 2013'
__credits__ = ['Donovan Parks']
__license__ = 'GPL3'
__version__ = '1.0.0'
__maintainer__ = 'Donovan Parks'
__email__ = 'donovan.parks@gmail.com'
__status__ = 'Development'

import os
import sys
import argparse
import ntpath

from readConfig import ReadConfig
from bwaUtils import mapPair, mapSingle

import pysam

class ClassifyBWA(object):
  def __init__(self):
    self.unclassifiedId = -1
    self.unclassifiedStr = 'k__unclassified;p__unclassified;c__unclassified;o__unclassified;f__unclassified;g__unclassified;s__unclassified;id__unclassified;'
    self.ggDB = '/srv/db/gg/2013_05/gg_13_5_otus/rep_set/##_otus.fasta'
    self.taxonomyFile = '/srv/db/gg/2013_05/gg_13_5_otus/taxonomy/##_otu_taxonomy.full.txt'

  def readTaxonomy(self, taxonomyFile):
    ggIdToTaxonomy = {}
    for line in open(taxonomyFile):
      lineSplit = line.split('\t')
      ggIdToTaxonomy[lineSplit[0]] = lineSplit[1].rstrip()

    return ggIdToTaxonomy

  def readPairedBAM(self, bamFile):
    # read compressed BAM file and report basic statistics
    bam = pysam.Samfile(bamFile, 'rb')

    # find all reads that mapped to a 16S sequence
    readsMappedTo16S_1 = {}
    readsMappedTo16S_2 = {}
    for read in bam.fetch(until_eof=True):
      if read.is_secondary:
        print read.qname
        continue

      bMultipleTopHits = False
      for tag in read.tags:
        if tag[0] == 'X0' and int(tag[1]) > 1:
          bMultipleTopHits = True
          break

      if bMultipleTopHits or read.is_unmapped or (read.mapq <= self.mappingQualityThreshold) or (read.alen < self.minLength):
        ggId = self.unclassifiedId
      else:
        ggId = bam.getrname(read.tid)

      if read.is_read1:
        readsMappedTo16S_1[read.qname + '/1'] = ggId
      elif read.is_read2:
        readsMappedTo16S_2[read.qname + '/2'] = ggId

    bam.close()

    return readsMappedTo16S_1, readsMappedTo16S_2

  def readSingleBAM(self, bamFile):
    # read compressed BAM file and report basic statistics
    bam = pysam.Samfile(bamFile, 'rb')

    # find all reads that mapped to a 16S sequence
    readsMappedTo16S = {}
    for read in bam.fetch(until_eof=True):
      if read.is_secondary:
        continue

      bMultipleTopHits = False
      for tag in read.tags:
        if tag[0] == 'X0' and int(tag[1]) > 1:
          bMultipleTopHits = True
          break

      if bMultipleTopHits or read.is_unmapped or (read.mapq <= self.mappingQualityThreshold) or (read.alen < self.minLength):
        readsMappedTo16S[read.qname] = self.unclassifiedId
      else:
        readsMappedTo16S[read.qname] = bam.getrname(read.tid)

    bam.close()

    return readsMappedTo16S

  def writeClassification(self, filename, mappedReads, ggIdToTaxonomy, bAppend = False):
    if bAppend:
      fout = open(filename, 'a')
    else:
      fout = open(filename, 'w')

    for refName in mappedReads:
      ggId = mappedReads[refName]
      if ggId != self.unclassifiedId:
        fout.write(refName + '\t' + ggIdToTaxonomy[ggId] + '\n')
      else:
        fout.write(refName + '\t' + self.unclassifiedStr + '\n')
    fout.close()

  def processPairs(self, pairs, ggIdToTaxonomy, outputDir, prefix):
    for i in xrange(0, len(pairs), 2):
      pair1 = pairs[i]
      pair2 = pairs[i+1]

      print 'Identifying 16S sequences in paired-end reads: ' + pair1 + ', ' + pair2

      # write out classifications for paired-end reads with both ends identified as 16S
      pair1Base = ntpath.basename(pair1)
      bamFile = prefix + '.' + pair1Base[0:pair1Base.rfind('.')] + '.intersect.16S.bam'
      readsMappedTo16S_1, readsMappedTo16S_2  = self.readPairedBAM(bamFile)

      output = prefix + '.' + pair1Base[0:pair1Base.rfind('.')] + '.intersect.16S.tsv'
      print '  Paired results written to: ' + output
      self.writeClassification(output, readsMappedTo16S_1, ggIdToTaxonomy)
      self.writeClassification(output, readsMappedTo16S_2, ggIdToTaxonomy, bAppend = True)
      
      # write out classifications for paired-ends reads with only one end identified as 16S
      bamFile = prefix + '.' + pair1Base[0:pair1Base.rfind('.')] + '.difference.16S.bam'
      readsMappedTo16S = self.readSingleBAM(bamFile)
      
      output = prefix + '.' + pair1Base[0:pair1Base.rfind('.')] + '.difference.16S.tsv'
      print '  Singleton results written to: ' + output
      self.writeClassification(output, readsMappedTo16S, ggIdToTaxonomy)

  def processSingles(self, singles, ggIdToTaxonomy, outputDir, prefix):
    for i in xrange(0, len(singles)):
      seqFile = singles[i]

      print 'Identifying 16S sequences in single-end reads: ' + seqFile

      singleBase = ntpath.basename(seqFile)
      bamFile = prefix + '.' + singleBase[0:singleBase.rfind('.')] + '.16S.bam'
      readsMappedTo16S = self.readSingleBAM(bamFile)

      output = prefix + '.' + singleBase[0:singleBase.rfind('.')] + '.16S.tsv'
      print '  Classification results written to: ' + output
      self.writeClassification(output, readsMappedTo16S, ggIdToTaxonomy)

  def run(self, configFile, otu, mappingQual, minLength, threads):
    rc = ReadConfig()
    projectParams, sampleParams = rc.readConfig(configFile, outputDirExists = True)
    
    # check if classification directory already exists
    if not os.path.exists(projectParams['output_dir'] + 'classified'):
      os.makedirs(projectParams['output_dir'] + 'classified')
    else:
      rtn = raw_input('Remove previously classified reads (Y or N)? ')
      if rtn.lower() == 'y' or rtn.lower() == 'yes':
        files = os.listdir(projectParams['output_dir'] + 'classified')
        for f in files:
          os.remove(projectParams['output_dir'] + 'classified/' + f)
      else:
        sys.exit()

    self.mappingQualityThreshold = mappingQual
    self.minLength = minLength

    taxonomyFile = self.taxonomyFile.replace('##', str(otu), 1)
    ggIdToTaxonomy = self.readTaxonomy(taxonomyFile)

    ggDB = self.ggDB.replace('##', str(otu), 1)
    
    print 'Classifying reads with: ' + ggDB
    print 'Assigning taxonomy with: ' + taxonomyFile
    print 'Threads: ' + str(threads)
    print ''

    if not os.path.exists(ggDB + '.amb'):
      print 'Indexing GreenGenes DB:'
      os.system('bwa index -a is ' + ggDB)
      print ''

    # map reads
    for sample in sampleParams:
      print 'Mapping sample: ' + sample
      outputDir = projectParams['output_dir']
      inputPrefix = outputDir + 'extracted/' + sample
      outputPrefix = outputDir + 'classified/' + sample
      pairs = sampleParams[sample]['pairs']
      singles = sampleParams[sample]['singles']

      for i in xrange(0, len(pairs), 2):
        pair1Base = ntpath.basename(pairs[i])
        pair1File = inputPrefix + '.' + pair1Base[0:pair1Base.rfind('.')] + '.intersect.SSU.fasta'

        pair2Base = ntpath.basename(pairs[i+1])
        pair2File = inputPrefix + '.' + pair2Base[0:pair2Base.rfind('.')] + '.intersect.SSU.fasta'

        bamPrefix = ntpath.basename(pairs[i])
        bamPrefixFile = outputPrefix + '.' + bamPrefix[0:bamPrefix.rfind('.')] + '.intersect.16S'
        mapPair(ggDB, pair1File, pair2File, bamPrefixFile, threads)
        
        diffFile = inputPrefix + '.' + pair1Base[0:pair1Base.rfind('.')] + '.difference.SSU.fasta'
        bamPrefixFile = outputPrefix + '.' + bamPrefix[0:bamPrefix.rfind('.')] + '.difference.16S'
        mapSingle(ggDB, diffFile, bamPrefixFile, threads)
        
      for i in xrange(0, len(singles)):
        singleBase = ntpath.basename(singles[i])
        singleFile = inputPrefix + '.' + singleBase[0:singleBase.rfind('.')] + '.SSU.fasta'

        bamPrefixFile = outputPrefix + '.' + singleBase[0:singleBase.rfind('.')] + '.16S'
        mapSingle(ggDB, singleFile, bamPrefixFile, threads)
        
      print '************************************************************'

    # classify reads
    for sample in sampleParams:
      print 'Classifying sample: ' + sample
      outputDir = projectParams['output_dir'] + 'classified/'
      prefix = outputDir + sample
      pairs = sampleParams[sample]['pairs']
      singles = sampleParams[sample]['singles']

      # identify 16S sequences in paired-end reads
      self.processPairs(pairs, ggIdToTaxonomy, outputDir, prefix)

      # identify 16S sequences in single-end reads
      self.processSingles(singles, ggIdToTaxonomy, outputDir, prefix)

      print ''

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Classify 16S fragments by mapping them to the GreenGenes DB with BWA.",
                                      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('config_file', help='project config file.')
  parser.add_argument('otu', help='GreenGenes DB to use for classification (choices: 94, 97, 99)', type=int, choices=[94, 97, 99], default=97)
  parser.add_argument('-m', '--map_quality', help='mapping quality required to treat read as classified (default: 10)', type=int, default=10)
  parser.add_argument('-l', '--min_length', help='minimum required alignment length to tread read as classified (default: 90)', type=int, default=90)
  parser.add_argument('-t', '--threads', help='number of threads', type=int, default = 1)

  args = parser.parse_args()

  classifyBWA = ClassifyBWA()
  classifyBWA.run(args.config_file, args.otu, args.map_quality, args.min_length, args.threads)