''' 
Copyright (C) 2011-2012 German Aerospace Center DLR
(Deutsches Zentrum fuer Luft- und Raumfahrt e.V.), 
Institute of System Dynamics and Control
All rights reserved.

This file is part of PySimulator.

PySimulator is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PySimulator is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with PySimulator. If not, see www.gnu.org/licenses.
'''

'''
Created on 05.04.2012

@author: otter
'''
import numpy.polynomial.polynomial
import sys
import math
from Plugins.Algorithms.Control import Misc


def transformRootsToPoly2(roots):
    """
    Transforms a vector of n conjugate complex roots to a
    (n//2, 3) real matrix of coefficients of 2nd order polynomials

    It is assumed that the roots[i] are the roots of a real-valued polynomial:

        product(s - roots[i])

    and the roots[i] are conjugate complex pairs. The roots are then transformed
    to a product of real valued second order polynomials:

        product(s**2 + c[j,1]*s + c[j,0])

    with j = i//2 and the matrix c of coefficients is returned.
    The coefficients are calculated as:

       c[j,0] = roots[i].real**2 + roots[i].imag**2
       c[j,1] = -2*roots[i].real

    It is checked whether the roots are conjugate complex numbers, that is
       roots[i].conj() == roots[i+1]

    Input arguments:
      roots: Vector of conjugate complex roots

    Return:
      c[:,2]: Matrix of second order polynomial coefficients.
    """
    nroots = len(roots)
    np     = nroots // 2

    # Check that all roots are conjugate complex pairs
    if (nroots % 2) <> 0:
        raise ValueError("Number of roots must be even.")
    r1 = numpy.array( roots[0:nroots:2] )
    r2 = numpy.array( roots[1:nroots:2] )
    eps = 100.0*sys.float_info.epsilon
    isConj = numpy.abs(r1.conj() - r2) < eps*numpy.max(
                                            numpy.vstack( (numpy.ones(np), numpy.abs(r1.real) )
                                         ), 0)
    if not numpy.alltrue(isConj):
        raise ValueError("Vector of roots are not all conjugate complex numbers:\n"+
                         "roots = " + str(roots))

    # Compute polynomial coefficients
    c = numpy.zeros((np,2))
    c[:,0] = (r1*r2).real
    c[:,1] = (-(r1+r2)).real
    return c


class ZerosAndPolesSISO:
    """
    Representation of a SISO Linear Time Invariant (LTI) system with zeros, poles, gains.

    A single input, single output LTI system generated by this class is defined as a
    transfer function of either of the two forms:

    (1) Transfer function described with gain, zeros, and poles,
        defined with a tuple:

            (k, z, p)

        where k is a real number, p and z are complex vectors,
        and this data defines the following transfer function:

                        product(s - z[i])
            y(s) = k * ------------------- * u(s)
                        product(s - p[i])

        There is the restriction that an element of z and p
        is either real or that two elements following directly each
        other must be conjugate complex pairs.

    (2) Transfer function described with real coefficients of first and second
        order polynomials, defined with a tuple:

            (k, n1, n2, d1, d2)

        where k is a real number, n1, d1 are real vectors,
        n2, d2 are real matrices with two columns,
        and this data defines the following transfer function:

                        product(s + n1[i]) * product(s**2 + n2[i,1]*s + n2[i,0])
            y(s) = k * ---------------------------------------------------------- * u(s)
                        product(s + d1[i]) * product(s**2 + d2[i,1]*s + d2[i,0])

    Internally, form (1) is transformed to form (2), and form(2) is
    described by numpy arrays. The reason to use form (2) is that
    systems of form (2) and systems that are generated by operations
    on form (2) (e.g. connecting systems) can always be represented
    as a StateSpace object with real coefficient matrices A,B,C,D.
    If instead a form (1) description would be used internally, operations
    on such a form might result in a state space system with complex
    coefficient matrices, due to numerical inaccuracies.

    Attributes:
       k, n1, n2, d1, d2, z, p

    Functions:
       __init__
       __str__
       poles
       zeros
       evaluate_at_s
       frequencyResponse
    """

    def __init__(self, zpk):
        """
        Initialize a ZeroAndPole object

        Input arguments:
          zpk: (gain, zeros, poles) of object as tuple (for details see ZerosAndPolesSISO.__docu__)
        """
        # Define defaults for internal object variables
        self.k  = 0
        self.n1 = None  # [a]    : a + s
        self.n2 = None  # [a,b,1]: a + b*s + 1*s**2
        self.d1 = None  # [a]    : a + s
        self.d2 = None  # [a,b,1]: a + b*s + 1*s**2
        self.z  = None  # vector of complex zeros
        self.p  = None  # vector of complex poles

        # Store input data
        if len(zpk) == 5:
            # form (2): Store internally and transform to numpy arrays if necessary
            self.k  = float(zpk[0])
            self.n1 = numpy.array(zpk[1], dtype=numpy.float, ndmin=1)
            self.n2 = numpy.array(zpk[2], dtype=numpy.float, ndmin=2)
            self.d1 = numpy.array(zpk[3], dtype=numpy.float, ndmin=1)
            self.d2 = numpy.array(zpk[4], dtype=numpy.float, ndmin=2)
            if self.n2.shape[1] != 2:
                raise ValueError("Second dimension of zpk[2] must be 2 and not "
                                 + str(self.n2.shape[1]) + "\n"
                                 + "(zpk[2] = " + str(zpk[2]) + ")")
            if self.d2.shape[1] != 2:
                raise ValueError("Second dimension of zpk[4] must be 2 and not "
                                 + str(self.d2.shape[1]) + "\n"
                                 "(zpk[4] = " + str(zpk[4]) + ")")

            def getRoots(r1, r2):
                """
                Get roots of a factorized polynomial

                Input arguments
                   r1: numpy vector describing the polynomial (s+r1[0])*(s+r1[1])*...
                   r2: (:,2) numpy matrix describing the polynomial
                       (s**2 + r2[1,1]*s + r2[1,0]*s)*(s**2 + r2[2,1]*s + r2[2,0])*....

                Output arguments
                   The roots of r1 and of r2 in one numpy vector
                """
                nr1  = len(r1)
                nr2  = len(r2)
                nr2c = 2*nr2
                r = numpy.zeros(nr1+nr2c, dtype=complex)
                if nr1 > 0:
                    r[0:nr1] = -r1
                if nr2 > 0:
                    for i in xrange(0,nr2):
                        r[nr1+2*i:nr1+2*i+2] = numpy.polynomial.polynomial.polyroots(
                                                    [r2[i,0], r2[i,1], 1.0] )
                return r

            self.z = getRoots(self.n1, self.n2)
            self.p = getRoots(self.d1, self.d2)

        elif len(zpk) == 3:
            # form (1): Copy in form (2) and transform to numpy arrays
            self.k = float(zpk[0])
            z = numpy.array(zpk[1], dtype=complex, ndmin=1)
            p = numpy.array(zpk[2], dtype=complex, ndmin=1)
            self.z = z
            self.p = p

            # Copy pure real zeros and poles
            self.n1 = -numpy.array ((z[z.imag == 0]).real, dtype=numpy.float)
            self.d1 = -numpy.array ((p[p.imag == 0]).real, dtype=numpy.float)

            # Transform conjugate complex zeros and poles to coefficients of 2nd order polynomials
            self.n2 = transformRootsToPoly2( z[z.imag <> 0.0] )
            self.d2 = transformRootsToPoly2( p[p.imag <> 0.0] )

        else:
            # error
            raise ValueError("Argument zpk must have 3 or 5 elements, but has %d elements" % len(zpk))


    def __str__(self):
        """
        String representation of a ZerosAndPolesSISO object
        """
        s = "\n"
        s += "   k = " + str(self.k) + "\n"
        s += "   z = " + str(self.z) + "\n"
        s += "   p = " + str(self.p) + "\n"
        return s

    def set_k(self, k_new):
        """
        Change gain k of zpk object to k_new
        """
        self.k = float(k_new)

    def poles(self):
        "Return poles of transfer function"
        return self.p

    def zeros(self):
        "Return zeros of transfer function"
        return self.z

    def evaluate_at_s(self, s, den_min=0.0):
        """
        Evaluate transfer function at given s-values

        Input arguments:
           s      : Complex value(s) at which the transfer function shall be evaluated
                    "s" must be either a scalar or "array-like"
           den_min: |denominator(s)| is limited by den_min in order to guard against
                    division by zero. Default = 0.0.

        Return argument:
           y: Value(s) of transfer function at s (same size as s)
        """
        # Determine whether s is a scalar or an array
        if isinstance(s,(int,float,complex)):
            ss  = complex(s)
            num = complex(self.k)
            den = 1.0+0.0j
            scalar = True
        else:
            # Assume it is array like and copy to a numpy array
            ss  = numpy.array(s, dtype=numpy.complex, copy=False)
            num = self.k*numpy.ones(ss.shape, dtype=numpy.complex)
            den =        numpy.ones(ss.shape, dtype=numpy.complex)
            scalar = False

        # Compute numerator
        for zj in self.n1:
            num *= ss + zj
        for (aj,bj) in self.n2:
            num *= aj + (bj+ss)*ss

        # Compute denominator
        for pj in self.d1:
            den *= ss + pj
        for (aj,bj) in self.d2:
            den *= aj + (bj+ss)*ss

        # Compute num/den
        abs_den = numpy.abs(den)
        if scalar:
            if abs_den >= den_min:
                den2 = den
            else:
                den2 = den_min
        else:
            den2 = numpy.select( [abs_den >= den_min*numpy.ones(den.shape)], [den], den_min )
        return num/den2


    def frequencyRange(self, f_range=None):
        """
        Compute useful frequency range

        Input arguments:
           f_range : Frequency range as tuple (f_min, f_max) in [Hz]
                     If f_range=None, the range is automatically selected (default)
                     Otherwise, the provided range is used

        Output arguments:
           (f_min, f_max): Useful minimal and maximal frequency range in [Hz]
        """
        return Misc.frequencyRange(self.z, self.p, f_range)


    def frequencyResponse(self, n=200, f_range=None, f_logspace=True):
        """
        Compute frequency response of transfer function y=zpk(s)

        Input arguments:
           n       : Number of result intervals (default = 200)
                     The result will have n+1 points.
           f_range : Frequency range as tuple (f_min, f_max) in [Hz]
                     If f_range=None, the range is automatically selected (default)
                     Otherwise, the provided range is used
           f_logspace: = True , if frequency values are logarithmically spaced (default)
                       = False, if frequency values are linearly spaced

        Output arguments:
           (f,y): Tuple of two complex vectors with n+1 elements per vector.
                  "f" is the float numpy vector of frequency points in [Hz] in logarithmic scale.
                  "y" is the complex numpy vector of response values y(s) with s=0+f*1j
        """
        # Determine frequency range
        (f_min,f_max) = self.frequencyRange(f_range)

        # Compute vector of frequency points
        if f_logspace:
            f = numpy.logspace( math.log10(f_min), math.log10(f_max), n+1 )
        else:
            f = numpy.linspace( f_min, f_max, n+1 )

        # Compute frequency response
        w      = numpy.zeros(len(f), dtype=complex)
        w.imag = Misc.from_Hz(f)
        y = self.evaluate_at_s(w, 1e-10)
        return (f,y)


class ZerosAndPoles:
    """
    Representation of a Linear Time Invariant (LTI) system with a matrix of zeros, poles, gains.
    """
    def __init__(self, zpk):
        """
        Initialize a ZeroAndPoles object

        Input arguments:
          zpk: [[zpk_ij]] Matrix of ZerosAndPoles_SISO object
               or matrix of (gain, zeros, poles) tuples
        """
        # Handle ZerosAndPolesSISO object
        if isinstance(zpk,ZerosAndPolesSISO):
            self.zpk = [[zpk]]
            self.nu  = 1
            self.ny  = 1
            return

        # Otherwise argument must be a list or a tuple
        if not isinstance(zpk, (list,tuple)):
            raise ValueError("Argument zpk must be a list or a tuple")

        # Distinguish whether a zpk object or a tuple of (k,z,p) is given
        self.nu  = len(zpk[0])
        self.ny  = len(zpk)
        self.zpk = zpk
        for i in xrange(0,self.ny):
            for j in xrange(0,self.nu):
                if not isinstance(self.zpk[i][j], ZerosAndPolesSISO):
                    self.zpk[i][j] = ZerosAndPolesSISO(self.zpk[i][j])


    def __getitem__(self,key):
        """
        Access an item as zpk[1,2]
        """
        if len(key) != 2:
            raise TypeError("Item must have two elements, e.g. [1,2]")
        if key[0] < 0 or key[0] >= self.ny:
            raise IndexError("Index is not in the allowed range")
        if key[1] < 0 or key[1] >= self.nu:
            raise IndexError("Index is not in the allowed range")
        return self.zpk[key[0]][key[1]]


    def __str__(self):
        """
        String representation of a ZerosAndPoles object
        """
        if self.nu == 1 and self.ny == 1:
            s = str(self.zpk[0][0])
        else:
            s = "\n"
            for i in xrange(0,self.ny):
                for j in xrange(0,self.nu):
                    s += " [{},{}] = {}\n".format(i, j, self.zpk[i][j])
        return s


    def evaluate_at_s(self, s, den_min=0.0, u_indices=None, y_indices=None):
        """
        Evaluate transfer function matrix at given s-values

        Input arguments:
           s        : Complex value(s) at which the transfer function matrix
                      shall be evaluated "s" must be either a scalar or "array-like"
           den_min  : |denominator(s)| is limited by den_min in order to guard against
           u_indices: If none, the transfer function matrix is computed from all inputs.
                      Otherwise, u_indices are the indices of the inputs for which
                      the matrix shall be computed. For example indices_u=(0,3,4)
                      means to compute transfer function matrix
                      from u[0], u[3], u[4] to the select outputs.
           y_indices: If none, the transfer function matrix is computed to all outputs.
                      Otherwise, y_indices are the indices of the outputs for which
                      the matrix shall be computed. For example indices_y=(0,3,4)
                      means to compute the transfer function matrix from selected inputs to
                      the outputs y[0], y[3], y[4].
                      division by zero. Default = 0.0.

        Return argument:
           Y: [ny,nu] matrix where every entry is a numpy vector representing the
              value(s) of the transfer function (i,j) at s (same size as s)
        """
        if u_indices == None:
            ui = range(0,self.nu)
        else:
            ui = u_indices
        if y_indices == None:
            yi = range(0,self.ny)
        else:
            yi = y_indices

        Y = [[ (self.zpk[i][j]).evaluate_at_s(s,den_min=den_min)
                  for i in yi]
                  for j in ui]
        return Y


    def frequencyResponse(self, n=200, f_range=None, f_logspace=True, u_indices=None, y_indices=None):
        """
        Compute frequency response of transfer function matrix Y=zpk(s)

        Input arguments:
           n         : Number of result intervals (default = 200)
                       The result will have n+1 points.
           f_range   : Frequency range as tuple (f_min, f_max) in [Hz]
                       If f_range=None, the range is automatically selected (default)
                       Otherwise, the provided range is used
           f_logspace: = True , if frequency values are logarithmically spaced (default)
                       = False, if frequency values are linearly spaced
           u_indices : If none, the frequency response is computed from all inputs.
                       Otherwise, u_indices are the indices of the inputs for which
                       the frequency response shall be computed. For example indices_u=(0,3,4)
                       means to compute the frequency responses from u[0], u[3], u[4] to the select outputs.
           y_indices : If none, the frequency response is computed to all outputs.
                       Otherwise, y_indices are the (user) indices of the outputs for which
                       the frequency response shall be computed. For example indices_y=(0,3,4)
                       means to compute the frequency responses from selected inputs to
                       the outputs y[0], y[3], y[4].

        Output arguments:
           (f,Y): Tuple of two complex vectors with n+1 elements per vector.
                  "f" is the float numpy vector of frequency points in [Hz] in logarithmic scale.
                  "Y" is the complex numpy vector of response values Y(s) with s=0+f*1j
        """
        # Determine frequency range
        if f_range != None:
            (f_min, f_max) = f_range
        else:
            if u_indices == None:
                ui = range(0,self.nu)
            else:
                ui = u_indices
            if y_indices == None:
                yi = range(0,self.ny)
            else:
                yi = y_indices

            (f_min, f_max) = (self.zpk[yi[0]][ui[0]]).frequencyRange()
            for i in yi:
                for j in ui:
                    (f_min_ij, f_max_ij) = (self.zpk[i][j]).frequencyRange()
                    f_min = min(f_min, f_min_ij)
                    f_max = max(f_max, f_max_ij)

        # Compute vector of frequency points
        if f_logspace:
            f = numpy.logspace( math.log10(f_min), math.log10(f_max), n+1 )
        else:
            f = numpy.linspace( f_min, f_max, n+1 )

        # Compute frequency response
        w      = numpy.zeros(len(f), dtype=complex)
        w.imag = Misc.from_Hz(f)
        Y = self.evaluate_at_s(w, 1e-10, ui, yi)
        return (f,Y)


if __name__ == "__main__":
    # Test "form(2)" to zpk
    zpk1 = ZerosAndPolesSISO((2.0, [2], [[1,2],[2,3]], [3,4], [[3,4],[5,6]]))
    print("zpk1 = " + str(zpk1) )

    # Test transformation of roots to polynomials
    roots = [1+2j,1-2j,4-3j,4+3j]
    poly2 = transformRootsToPoly2(roots)
    r1 = numpy.polynomial.polynomial.polyroots( [poly2[0,0], poly2[0,1], 1.0] )
    r2 = numpy.polynomial.polynomial.polyroots( [poly2[1,0], poly2[1,1], 1.0])
    print("poly2 = " + str(poly2))
    print("roots = " + str(roots))
    print("roots(poly2) = " + str(r1) + ", " + str(r2))

    # Test "form(1) to zpk
    zeros = [4.0, 2-3j, 2+3j]
    poles = [1+2j, 1-2j, 5.0, 6.0, 4.0-3j, 4.0+3j, 7]
    zpk2 = ZerosAndPolesSISO((3.1, zeros, poles))
    print("zpk2 = " + str(zpk2))

    # Test evaluate
    r1a = zpk2.evaluate_at_s(1+2j, 1e-15)
    r1b = zpk2.evaluate_at_s(2, 1e-15)
    r1c = zpk2.evaluate_at_s(3, 1e-15)
    print("r1 = " + str(r1a) + ", " + str(r1b) + "," + str(r1c))
    r2 = zpk2.evaluate_at_s([1+2j,2,3], 1e-15)
    print("r2 = " + str(r2))

    # Test zeros and poles
    zeros2 = zpk2.zeros()
    poles2 = zpk2.poles()
    print("input zeros = " + str(zeros))
    print("zeros = " + str(zeros2))
    print("input poles = " + str((poles)))
    print("poles = " + str(poles2))

    # Test frequency response
    (f,y) = zpk2.frequencyResponse(n=10)
    print("f = " + str(f))
    print("y = " + str(y))
    (f,y) = zpk2.frequencyResponse(n=10,f_logspace=False)
    print("f = " + str(f))
    print("y = " + str(y))

    # Test different MIMO ZerosAndPoles initialization
    zpk = ZerosAndPoles(zpk2)
    print("zpk = {}".format(zpk))
    zpk = ZerosAndPoles([[(3.2, zeros, poles)]])
    print("zpk = {}".format(zpk))

    # Test MIMO ZerosAndPoles
    zpk3 = ZerosAndPoles([[zpk2]])
    print("zpk3 = {}".format(zpk3))
    (f1,y1) = zpk2.frequencyResponse(n=10)
    (f2,y2) = zpk3.frequencyResponse(n=10)
    print("f1 = {}".format(f1))
    print("f2 = {}".format(f2))
    print("y1 = {}".format(y1))
    print("y2 = {}".format(y2))

    zpk4 = ZerosAndPoles([[zpk2, zpk2]])
    print("zpk4 = {}".format(zpk4))
    (f3,y3) = zpk4.frequencyResponse(n=10)
    print("f3 = {}".format(f3))
    print("y3 = {}".format(y3))

