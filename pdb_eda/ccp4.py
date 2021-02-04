# !/usr/bin/python3
"""
CCP4 Parser (pdb_eda.ccp4)
-------------------------------------------------------

This module provides methods to read and parse the CCP4 format files, returning ccp4 objects.
Format details of ccp4 can be found in http://www.ccp4.ac.uk/html/maplib.html.
"""

import warnings
import struct
import itertools

import urllib.request
import numpy as np

try:
    from . import cutils as utils
except ImportError:
    from . import utils

urlPrefix = "http://www.ebi.ac.uk/pdbe/coordinates/files/"
urlSuffix = ".ccp4"


def readFromPDBID(pdbid, verbose=False):
    """
    Creates :class:`pdb_eda.ccp4.DensityMatrix` object.

    :param str pdbid: PDB id.
    """
    return readFromURL(urlPrefix + pdbid.lower() + urlSuffix, pdbid, verbose)


def readFromURL(url, pdbid=None, verbose=False):
    """
    Creates :class:`pdb_eda.ccp4.DensityMatrix` object.

    :param str url: url.
    """
    if not pdbid:
        pdbid = url
    with urllib.request.urlopen(url) as urlHandle:
        return parse(urlHandle, pdbid, verbose)


def read(ccp4Filename, pdbid=None, verbose=False):
    """
    Creates :class:`pdb_eda.ccp4.DensityMatrix` object.

    :param str ccp4Filename: .ccp4 filename including path.
    """
    if not pdbid:
        pdbid = ccp4Filename
    with open(ccp4Filename, "rb") as fileHandle:
        return parse(fileHandle, pdbid, verbose)


def parse(handle, pdbid, verbose=False):
    """
    Creates :class:`pdb_eda.ccp4.DensityMatrix` object.

    :param handle: a file handle for .ccp4 file.
    """
    header = DensityHeader.fromFileHeader(handle.read(1024))
    endian = header.endian
    dataBuffer = handle.read()

    # Sanity check on file sizes
    if len(dataBuffer) != header.symmetryBytes + header.mapSize:
        assert header.symmetryBytes == 0 | len(
            dataBuffer) != header.mapSize, "Error: File contains suspicious symmetry records"
        assert header.mapSize == 0 | len(dataBuffer) != header.symmetryBytes, "Error: File contains no map data"
        assert len(dataBuffer) > header.symmetryBytes + header.mapSize, "Error: contains incomplete data"
        assert len(dataBuffer) < header.symmetryBytes + header.mapSize, "Error: File contains larger than expected data"

    assert header.xlength != 0.0 or header.ylength != 0.0 or header.zlength != 0.0, "Error: Cell dimensions are all 0, Map file will not align with other structures"

    if header.nintervalX == 0 & header.ncrs[0] > 0:
        header.nintervalX = header.ncrs[0] - 1
        if verbose: warnings.warn("Fixed number of X interval")
    if header.nintervalY == 0 & header.ncrs[1] > 0:
        header.nintervalY = header.ncrs[1] - 1
        if verbose: warnings.warn("Fixed number of Y interval")
    if header.nintervalZ == 0 & header.ncrs[2] > 0:
        header.nintervalZ = header.ncrs[2] - 1
        if verbose: warnings.warn("Fixed number of Z interval.")

    if header.col2xyz == 0 & header.row2xyz == 0 & header.sec2xyz == 0:
        header.col2xyz = 1
        header.row2xyz = 2
        header.sec2xyz = 3
        if verbose: warnings.warn("Mappings from column/row/section to xyz are all 0, set to 1, 2, 3 instead.")

    header.symmetry = dataBuffer[0:header.symmetryBytes]
    mapData = dataBuffer[header.symmetryBytes:len(dataBuffer)]

    numBytes = int(len(mapData) / 4)
    densities = struct.unpack(endian + numBytes * 'f', mapData)
    origin = header.origin

    # Calculate some statistics
    #sigma = np.std(densities)
    #mean = np.mean(densities)
    #median = np.median(densities)
    #mode = 0  # statistics.mode(densities)
    #print('mean, median, mode, sigma, header rmsd, difference of the last two: ', mean, median, mode, sigma, header.rmsd, sigma - header.rmsd)

    return DensityMatrix(header, origin, densities, pdbid)


class DensityHeader(object):
    """:class:`pdb_eda.ccp4.DensityHeader` that stores information about ccp4 header."""

    @classmethod
    def fromFileHeader(cls, fileHeader):
        """RETURNS :class:`pdb_eda.ccp4.DensityHeader` object given the fileHeader.

        :param fileHeader: ccp4 file header.
        :type fileHeader: binary header section of a ccp4 file
        """

        # Test for endianness
        mode = int.from_bytes(fileHeader[12:16], byteorder='little')
        endian = '<' if 0 <= mode <= 6 else '>'

        # Header
        headerFormat = endian + 10 * 'i' + 6 * 'f' + 3 * 'i' + 3 * 'f' + 3 * 'i' + 27 * 'f' + 4 * 'c' + 'ifi'
        headerTuple = struct.unpack(headerFormat, fileHeader[:224])
        #print(headerTuple)
        labels = fileHeader[224:]  # Labels in header
        labels = labels.replace(b' ', b'')

        header = DensityHeader(headerTuple, labels, endian)
        return header

    def __init__(self, headerTuple, labels, endian):
        """
        Initialize the :class:`pdb_eda.ccp4.DensityHeader` object, assign values to data members accordingly,
         and calculate some metrics that will be used frequently.

        :param headerTuple: The ccp4 header information (excluding labels) in a tuple.
        :param labels: The labels field in a ccp4 header.
        :param endian: The endianness of the file.
        """
        self.ncrs = headerTuple[0:3]
        #Number of Columns    (fastest changing in map)
        #Number of Rows
        #Number of Sections   (slowest changing in map)

        self.mode = headerTuple[3]
        self.endian = endian
        #Data type
        #    0 = envelope stored as signed bytes (from -128 lowest to 127 highest)
        #    1 = Image     stored as Integer*2
        #    2 = Image     stored as Reals
        #    3 = Transform stored as Complex Integer*2
        #    4 = Transform stored as Complex Reals
        #    5 == 0

        #    Note: Mode 2 is the normal mode used in the CCP4 programs. Other modes than 2 and 0
        #        may NOT WORK

        self.crsStart = headerTuple[4:7]  # Number of first COLUMN, ROW, and SECTION in map
        self.nintervalX = headerTuple[7]  # Number of intervals along X
        self.nintervalY = headerTuple[8]  # Number of intervals along Y
        self.nintervalZ = headerTuple[9]  # Number of intervals along Z
        self.xlength = headerTuple[10]  # Cell Dimensions (Angstroms)
        self.ylength = headerTuple[11]  # ''
        self.zlength = headerTuple[12]  # ''
        self.alpha = headerTuple[13]  # Cell Angles     (Degrees)
        self.beta = headerTuple[14]  # ''
        self.gamma = headerTuple[15]  # ''
        self.col2xyz = headerTuple[16]  # Which axis corresponds to Cols.  (1,2,3 for X,Y,Z)
        self.row2xyz = headerTuple[17]  # Which axis corresponds to Rows   (1,2,3 for X,Y,Z)
        self.sec2xyz = headerTuple[18]  # Which axis corresponds to Sects. (1,2,3 for X,Y,Z)
        self.densityMin = headerTuple[19]  # Minimum density value
        self.densityMax = headerTuple[20]  # Maximum density value
        self.densityMean = headerTuple[21]  # Mean    density value    (Average)
        self.spaceGroup = headerTuple[22]  # Space group number
        self.symmetryBytes = headerTuple[23]  # Number of bytes used for storing symmetry operators
        self.skewFlag = headerTuple[24]  # Flag for skew transformation, =0 none, =1 if foll
        self.skewMat = headerTuple[25:34]  # Skew matrix S (in order S11, S12, S13, S21 etc) if LSKFLG .ne. 0.
        self.skewTrans = headerTuple[34:37]
        #Skew translation t if LSKFLG .ne. 0.
        #            Skew transformation is from standard orthogonal
        #            coordinate frame (as used for atoms) to orthogonal
        #            map frame, as: Xo(map) = S * (Xo(atoms) - t)

        self.futureUse = headerTuple[37:49]
        #(some of these are used by the MSUBSX routines in MAPBRICK, MAPCONT and FRODO) (all set to zero by default)
        self.originEM = headerTuple[49:52]
        #Use ORIGIN records rather than old crsStart records as in http://www2.mrc-lmb.cam.ac.uk/image2000.html
        #The ORIGIN field is only used by the EM community, and has undefined meaning for non-orthogonal maps and/or
        #non-cubic voxels, etc.

        self.mapChar = headerTuple[52:56]  # Character string 'MAP ' to identify file type
        self.machineStamp = headerTuple[56]  # Machine stamp indicating the machine type which wrote file
        self.rmsd = headerTuple[57]  # Rms deviation of map from mean density
        self.nLabel = headerTuple[58]  # Number of labels being used
        self.labels = labels

        self.mapSize = self.ncrs[0] * self.ncrs[1] * self.ncrs[2] * 4
        self.xyzLength = [self.xlength, self.ylength, self.zlength]
        self.xyzInterval = [self.nintervalX, self.nintervalY, self.nintervalZ]
        self.gridLength = [x/y for x, y in zip(self.xyzLength, self.xyzInterval)]

        indices = [0, 0, 0]
        indices[self.col2xyz - 1] = 0
        indices[self.row2xyz - 1] = 1
        indices[self.sec2xyz - 1] = 2
        self.map2xyz = indices
        self.map2crs = [self.col2xyz - 1, self.row2xyz - 1, self.sec2xyz - 1]

        self.crsInterval = [self.xyzInterval[self.map2crs[ind]] for ind in range(3)]


        alpha = np.pi / 180 * self.alpha
        beta = np.pi / 180 * self.beta
        gamma = np.pi / 180 * self.gamma
        self.unitVolume = self.xlength * self.ylength * self.zlength / self.nintervalX / self.nintervalY / self.nintervalZ * \
                          np.sqrt(1 - np.cos(alpha) ** 2 - np.cos(beta) ** 2 - np.cos(gamma) ** 2 + 2 * np.cos(alpha) * np.cos(beta) * np.cos(gamma))

        ## A reusable part in the cell volumn calculation
        temp = np.sqrt(1 - np.cos(alpha) ** 2 - np.cos(beta) ** 2 - np.cos(gamma) ** 2 + 2 * np.cos(alpha) * np.cos(beta) * np.cos(gamma))
        self.orthoMat = [[self.xlength, self.ylength * np.cos(gamma), self.zlength * np.cos(beta)],
                         [0, self.ylength * np.sin(gamma), self.zlength * (np.cos(alpha) - np.cos(beta) * np.cos(gamma)) / np.sin(gamma)],
                         [0, 0, self.zlength * temp / np.sin(gamma)]]

        self.deOrthoMat = np.linalg.inv(self.orthoMat)
        self.deOrthoMat[abs(self.deOrthoMat) < 1e-10] = 0.0

        #self.deOrthoMat = [[1/self.xlength, - np.cos(gamma) / np.sin(gamma) / self.xlength,
        #                    (np.cos(gamma) * (np.cos(alpha) - np.cos(beta) * np.cos(gamma)) / np.sin(gamma) - np.cos(beta) * np.sin(gamma)) / self.xlength / temp],
        #                   [0, 1/np.sin(gamma)/self.ylength, - (np.cos(alpha) - np.cos(beta) * np.cos(gamma)) / np.sin(gamma) / self.ylength / temp],
        #                   [0, 0, np.sin(gamma) / self.zlength / temp]]

        self.origin = self._calculateOrigin()

        ncrs = [i for i in self.ncrs]
        if self.xyzInterval[self.col2xyz - 1] < self.ncrs[0]:
            ncrs[0] = self.xyzInterval[self.col2xyz - 1]
        if self.xyzInterval[self.row2xyz - 1] < self.ncrs[1]:
            ncrs[1] = self.xyzInterval[self.row2xyz - 1]
        if self.xyzInterval[self.sec2xyz - 1] < self.ncrs[2]:
            ncrs[2] = self.xyzInterval[self.sec2xyz - 1]
        self.uniqueNcrs = ncrs


    def _calculateOrigin(self):
        """
        Calculate the xyz coordinates from the header information.

        :return: xyz coordinates.
        :rtype: A :py:obj:`list` of :py:obj:`float`.
        """
        # Orthogonalization matrix for calculation between fractional coordinates and orthogonal coordinates
        # Formula based on 'Biomolecular Crystallography' by Bernhard Rupp, p233

        if self.futureUse[-3] == 0.0 and self.futureUse[-2] == 0.0 and self.futureUse[-1] == 0.0:
            origin = np.dot(self.orthoMat, [self.crsStart[self.map2xyz[i]] / self.xyzInterval[i] for i in range(3)])
        else:
            origin = [self.originEM[i] for i in range(3)]

        return origin

    def validCRS(self, crsCoord):
        """
        Check if the crs coordinate is valid (within the range of data).

        :param crsCoord: crs coordinates.
        :type crsCoord: A :py:obj:`list` of :py:obj:`int`
        """
        for ind in range(3):
            if crsCoord[ind] < 0 or crsCoord[ind] >= self.ncrs[ind]:
                crsCoord[ind] -= int(np.floor(crsCoord[ind] / self.crsInterval[ind]) * self.crsInterval[ind])

            if self.ncrs[ind] <= crsCoord[ind] < self.crsInterval[ind]:
                return False

        return True

    def xyz2crsCoord(self, xyzCoord):
        """
        Convert the xyz coordinates into crs coordinates.


        :param xyzCoord: xyz coordinates.
        :type xyzCoord: A :py:obj:`list` of :py:obj:`float`

        :return: crs coordinates.
        :rtype: A :py:obj:`list` of :py:obj:`int`.
        """
        if self.alpha == self.beta == self.gamma == 90:
            crsGridPos = [int(round((xyzCoord[i] - self.origin[i]) / self.gridLength[i])) for i in range(3)]
        else:
            fraction = np.dot(self.deOrthoMat, xyzCoord)
            crsGridPos = [int(round(fraction[i] * self.xyzInterval[i])) - self.crsStart[self.map2xyz[i]] for i in range(3)]
        return [crsGridPos[self.map2crs[i]] for i in range(3)]

    def crs2xyzCoord(self, crsCoord):
        """
        Convert the crs coordinates into xyz coordinates.

        :param crsCoord: crs coordinates.
        :type crsCoord: A :py:obj:`list` of :py:obj:`int`

        :return: xyz coordinates.
        :rtype: A :py:obj:`list` of :py:obj:`float`.
        """
        if self.alpha == self.beta == self.gamma == 90:
            return [crsCoord[self.map2xyz[i]] * self.gridLength[i] + self.origin[i] for i in range(3)]
        else:
            return np.dot(self.orthoMat, [(crsCoord[self.map2xyz[i]] + self.crsStart[self.map2xyz[i]]) / self.xyzInterval[i] for i in range(3)])


class DensityMatrix:
    """:class:`pdb_eda.ccp4.DensityMatrix` that stores data and methods of a ccp4 file."""

    def __init__(self, header, origin, density, pdbid):
        """
        Initialize the :class:`pdb_eda.ccp4.DensityMatrix` object.

        :param header: the :class:`pdb_eda.ccp4.DensityHeader` object of the density matrix.
        :param origin: the xyz coordinates of the origin of the first number of the density data.
        :param density: the density data as a 1-d list.
        :return: :class:`pdb_eda.ccp4.DensityMatrix` object.
        """
        self.pdbid = pdbid
        self.header = header
        self.origin = origin
        self.densityArray = density
        self.density = np.array(density).reshape(header.ncrs[2], header.ncrs[1], header.ncrs[0])
        self._meanDensity = None
        self._stdDensity = None

    @property
    def meanDensity(self):
        if self._meanDensity == None:
            self._meanDensity = np.mean(self.densityArray)
        return self._meanDensity

    @property
    def stdDensity(self):
        if self._stdDensity == None:
            self._stdDensity = np.std(self.densityArray)
        return self._stdDensity

    def getPointDensityFromCrs(self, crsCoord):
        """
        Get the density of a point.

        :param crsCoord: crs coordinates.
        :type crsCoord: A :py:obj:`list` of :py:obj:`int`
        """
        return self.density[crsCoord[2], crsCoord[1], crsCoord[0]] if self.header.validCRS(crsCoord) else 0

    def getPointDensityFromXyz(self, xyzCoord):
        """
        Get the density of a point.

        :param xyzCoord: xyz coordinates.
        :type xyzCoord: A :py:obj:`list` of :py:obj:`float`
        """
        return self.getPointDensityFromCrs(self.header.xyz2crsCoord(xyzCoord))

    def getSphereCrsFromXyz(self, xyzCoord, radius, densityCutoff=0):
        """
        Calculate a list of crs coordinates that within a given distance of a point.

        :param xyzCoord: xyz coordinates.
        :type xyzCoord: A :py:obj:`list` of :py:obj:`float`
        :param float radius: the radius.
        :param  float densityCutoff: a density cutoff for all the points wants to be included.
                Default 0 means include every point within the radius.
                If cutoff < 0, include only points with density < cutoff.
                If cutoff > 0, include only points with density > cutoff.

        :return: A :py:obj:`list` of crs coordinates.
        """
        crsCoord = self.header.xyz2crsCoord(xyzCoord)
        crsRadius = self.header.xyz2crsCoord(self.origin + [radius, radius, radius])
        crsCoordList = []
        for crs in itertools.product(range(crsCoord[0] - crsRadius[0]-1, crsCoord[0] + crsRadius[0]+1),
                                     range(crsCoord[1] - crsRadius[1]-1, crsCoord[1] + crsRadius[1]+1),
                                     range(crsCoord[2] - crsRadius[2]-1, crsCoord[2] + crsRadius[2]+1)):
            density = self.getPointDensityFromCrs(crs)
            if 0 < densityCutoff < density or density < densityCutoff < 0 or densityCutoff == 0:
                xyz = self.header.crs2xyzCoord(crs)
                if np.sqrt((xyz[0] - xyzCoord[0])**2 + (xyz[1] - xyzCoord[1])**2 + (xyz[2] - xyzCoord[2])**2) <= radius:
                    crsCoordList.append(crs)

        return crsCoordList

    def getTotalDensityFromXyz(self, xyzCoord, radius, densityCutoff=0):
        """
        Calculate the total density of a sphere.

        :param xyzCoord: xyz coordinates.
        :type xyzCoord: A :py:obj:`list` of xyz coordinates
        :param float radius: the radius.
        :param float densityCutoff: a density cutoff for all the points to include.
                Default 0 means include every point within the radius.
                If cutoff < 0, include only points with density < cutoff.
                If cutoff > 0, include only points with density > cutoff.
        """
        crsCoordList = self.getSphereCrsFromXyz(xyzCoord, radius, densityCutoff)
        return sum(self.getPointDensityFromCrs(crs) for crs in crsCoordList)

    def findAberrantBlobs(self, xyzCoords, radius, densityCutoff=0):
        """
        Within a given radius, find and aggregate all neighbouring aberrant points into blobs (red/green meshes).

        :param xyzCoords: xyz coordinates.
        :type xyzCoords: A :py:obj:`list` of a single xyz coordinate or a list of xyz coordinates.
        :param float radius: the search radius.
        :param float densityCutoff: A density cutoff for all the points wants to be included.
                Default 0 means include every point within the radius.
                If cutoff < 0, include only points with density < cutoff.
                If cutoff > 0, include only points with density > cutoff.

        :return: A list of aberrant blobs described by their xyz centroid, total density, and volume.
        :rtype: A :py:obj:`list` of :class:`pdb_eda.ccp4.DensityBlob` object.
        """
        if not isinstance(xyzCoords[0], (np.floating, float)): # test if xyzCoords is a single xyzCoord or a list of them.
            if len(xyzCoords) > 1:
                crsCoordList = list({tuple(crsCoord) for xyzCoord in xyzCoords for crsCoord in self.getSphereCrsFromXyz(xyzCoord, radius, densityCutoff)})
            else:
                crsCoordList = self.getSphereCrsFromXyz(xyzCoords[0], radius, densityCutoff)
        else:
            crsCoordList = self.getSphereCrsFromXyz(xyzCoords, radius, densityCutoff)

        return self.createBlobList(crsCoordList)

    def createBlobList(self, crsList):
        """
        Calculates a list of blobs from a given crsList.

        :param crsList: a crs list.
        :return: blobList is a list of blobs.
        :rtype: A :py:obj:`list` of :class:`pdb_eda.ccp4.DensityBlob` object.
        """
        crsLists = utils.createCrsLists(crsList)
        return [ DensityBlob.fromCrsList(crs_list, self.header, self.density) for crs_list in crsLists ]


class DensityBlob:
    """:class:`pdb_eda.ccp4.DensityBlob` that stores data and methods of a electron density blob."""

    def __init__(self, centroid, coordCenter, totalDensity, volume, crsList, header, densityMatrix):
        """
        Initialize a :class:`pdb_eda.ccp4.DensityBlob` object.

        :param centroid: the centroid of the blob.
        :param totalDensity: the totalDensity of the blob.
        :param volume: the volume of the blob = number of density units * unit volumes.
        :param crsList: the crs list of the blob.
        :param header: the header of the ccp4 file.
        :param densityMatrix: the entire density map that the blob belongs to.

        :return: A :class:`pdb_eda.ccp4.DensityBlob` object.
        """
        self.centroid = centroid
        self.coordCenter = coordCenter
        self.totalDensity = totalDensity
        self.volume = volume
        self.crsList = {tuple(crs) for crs in crsList}
        self.header = header
        self.densityMatrix = densityMatrix
        self.atoms = []


    @staticmethod
    def fromCrsList(crsList, header, densityMatrix):
        """
        The creator of a A :class:`pdb_eda.ccp4.DensityBlob` object.

        :param crsList: the crs list of the blob.
        :param header: the header of the ccp4 file.
        :param densityMatrix: the 3-d density matrix to use for calculating centroid etc, so the object does not have to have a density list data member.

        :return: A :class:`pdb_eda.ccp4.DensityBlob` object.
        """
        weights = [0, 0, 0]
        totalDen = 0
        for i, point in enumerate(crsList):
            density = densityMatrix[point[2], point[1], point[0]]
            pointXYZ = header.crs2xyzCoord(point)
            weights = [weights[i] + density * pointXYZ[i] for i in range(3)]
            totalDen += density

        centroidXYZ = [weight / totalDen for weight in weights]
        npoints = len(crsList)
        coordCenter = [sum(k) / npoints for k in zip(*[header.crs2xyzCoord(crs) for crs in crsList])]
        return DensityBlob(centroidXYZ, coordCenter, totalDen, header.unitVolume * len(crsList), crsList, header, densityMatrix)


    def __eq__(self, otherBlob):
        """
        Check if two blobs are the same, and overwrite the '==' operator for the :class:`pdb_eda.ccp4.DensityBlob` object.

        :param otherBlob: A :class:`pdb_eda.ccp4.DensityBlob` object.
        """
        if abs(self.volume - otherBlob.volume) >= 1e-6: return False
        if abs(self.totalDensity - otherBlob.totalDensity) >= 1e-6: return False
        for i in range(0, 3):
            if abs(self.centroid[i] - otherBlob.centroid[i]) >= 1e-6: return False

        return True

    def testOverlap(self, otherBlob):
        """
        Check if two blobs overlaps or right next to each other.

        :param otherBlob: A :class:`pdb_eda.ccp4.DensityBlob` object.
        :return: :py:obj:`True` or :py:obj:`False`.
        """
        #if any(x in self.crsList for x in otherBlob.crsList):
        #    return True
        #if np.any(scipy.spatial.distance.cdist(np.matrix(self.crsList), np.matrix(otherBlob.crsList)) <= np.sqrt(3)):
        if any(-1 <= x[0] - y[0] <= 1 and -1 <= x[1] - y[1] <= 1 and -1 <= x[2] - y[2] <= 1 for x in self.crsList for y in otherBlob.crsList):
            return True
        else:
            return False

    def merge(self, otherBlob):
        """
        Merge the given blob into the original blob.

        :param otherBlob: A :class:`pdb_eda.ccp4.DensityBlob` object.
        :return: :py:obj:`None`.
        """
        self.crsList.update(otherBlob.crsList)
        atoms = self.atoms + [atom for atom in otherBlob.atoms if atom not in self.atoms]
        newBlob = DensityBlob.fromCrsList(self.crsList, self.header, self.densityMatrix)

        self.__dict__.update(newBlob.__dict__)
        self.atoms = atoms

        # self.centroid = newBlob.centroid
        # self.totalDensity = newBlob.totalDensity
        # self.volume = newBlob.volume
        # self.crsList = newBlob.crsList
        # self.header = newBlob.header
        # self.densityMatrix = newBlob.densityMatrix
        # self.atoms = self.atoms + [atom for atom in otherBlob.atoms if atom not in self.atoms]



