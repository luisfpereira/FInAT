import numpy

from gem import Literal, ListTensor

from finat.fiat_elements import ScalarFiatElement
from finat.physically_mapped import PhysicallyMappedElement, Citations
from .wu_xu_fiat import WuXuRobustH3NC as WuXuRobustH3NC_fiat
from .wu_xu_fiat import WuXuH3NC as WuXuH3NC_fiat


class WuXuRobustH3NC(PhysicallyMappedElement, ScalarFiatElement):
    def __init__(self, cell, degree=None):
        if degree is None:
            degree = 7
        if degree != 7:
            raise ValueError("Degree must be 7 for robust Wu-Xu element")
        if Citations is not None:
            Citations().register("WuXu2019")
        super().__init__(WuXuRobustH3NC_fiat(cell))

    def basis_transformation(self, coordinate_mapping):
        J = coordinate_mapping.jacobian_at([1/3, 1/3])
        J = numpy.array([[J[0, 0], J[0, 1]],
                         [J[1, 0], J[1, 1]]])
        [[dxdxhat, dxdyhat], [dydxhat, dydyhat]] = J

        Thetainv = numpy.array(
            [[dxdxhat*dxdxhat, Literal(2) * dxdxhat * dydxhat, dydxhat*dydxhat],
             [dxdyhat * dxdxhat, dxdyhat * dydxhat + dxdxhat * dydyhat, dydxhat * dydyhat],
             [dxdyhat*dxdyhat, Literal(2) * dxdyhat * dydyhat, dydyhat*dydyhat]])
        nhats = coordinate_mapping.reference_normals()
        ns = coordinate_mapping.physical_normals()

        ts = coordinate_mapping.physical_tangents()

        thats = numpy.zeros((3, 2), dtype=object)
        for e in range(3):
            tancur = self.cell.compute_normalized_edge_tangent(e)
            for i in range(2):
                thats[e, i] = Literal(tancur[i])

        lens = coordinate_mapping.physical_edge_lengths()

        V = numpy.zeros((15, 15), dtype=object)

        for multiindex in numpy.ndindex(V.shape):
            V[multiindex] = Literal(V[multiindex])

        Gs = numpy.zeros((3, 2, 2), dtype='O')
        Ghats = numpy.zeros((3, 2, 2), dtype='O')
        Gammas = numpy.zeros((3, 3, 3), dtype='O')
        Gammainvhats = numpy.zeros((3, 3, 3), dtype='O')
        B1s = numpy.zeros((3, 2, 2), dtype='O')
        B2s = numpy.zeros((3, 3, 3), dtype='O')
        betas = numpy.zeros((3, 2), dtype='O')

        for e in range(3):
            nx = ns[e, 0]
            ny = ns[e, 1]
            nhatx = nhats[e, 0]
            nhaty = nhats[e, 1]
            tx = ts[e, 0]
            ty = ts[e, 1]
            thatx = thats[e, 0]
            thaty = thats[e, 1]

            Gs[e, :, :] = numpy.asarray([[nx, ny], [tx, ty]])
            Ghats[e, :, :] = numpy.asarray([[nhatx, nhaty],
                                            [thatx, thaty]])

            Gammas[e, :, :] = numpy.asarray(
                [[nx*nx, Literal(2)*nx*tx, tx*tx],
                 [nx*ny, nx*ty+ny*tx, tx*ty],
                 [ny*ny, Literal(2)*ny*ty, ty*ty]])

            Gammainvhats[e, :, :] = numpy.asarray(
                [[nhatx*nhatx, Literal(2)*nhatx*nhaty, nhaty*nhaty],
                 [nhatx*thatx, nhatx*thaty+nhaty*thatx, nhaty*thaty],
                 [thatx*thatx, Literal(2)*thatx*thaty, thaty*thaty]])

            B1s[e, :, :] = numpy.dot(Ghats[e],
                                     numpy.dot(J.T, Gs[e].T)) / lens[e]
            B2s[e, :, :] = numpy.dot(Gammainvhats[e],
                                     numpy.dot(Thetainv, Gammas[e])) / lens[e]

            betas[e, 0] = nx * B2s[e, 0, 1] + tx * B2s[e, 0, 2]
            betas[e, 1] = ny * B2s[e, 0, 1] + ty * B2s[e, 0, 2]

        for e in range(3):
            V[3*e, 3*e] = Literal(1)
            for i in range(2):
                for j in range(2):
                    V[3*e+1+i, 3*e+1+j] = J[j, i]

        V[10, 0] = Literal(-1)*B1s[1, 0, 1]
        V[11, 0] = Literal(-1)*B1s[2, 0, 1]
        V[9, 3] = Literal(-1)*B1s[0, 0, 1]
        V[11, 3] = B1s[2, 0, 1]
        V[9, 6] = B1s[0, 0, 1]
        V[10, 6] = B1s[1, 0, 1]

        for e in range(9, 12):
            V[e, e] = B1s[e-9, 0, 0]

        for e in range(12, 15):
            V[e, e] = B2s[e-12, 0, 0]

        V[13, 1] = Literal(-1)*betas[1, 0]
        V[13, 2] = Literal(-1)*betas[1, 1]
        V[14, 1] = Literal(-1)*betas[2, 0]
        V[14, 2] = Literal(-1)*betas[2, 1]
        V[12, 4] = Literal(-1)*betas[0, 0]
        V[12, 5] = Literal(-1)*betas[0, 1]
        V[14, 4] = betas[2, 0]
        V[14, 5] = betas[2, 1]
        V[12, 7] = betas[0, 0]
        V[12, 8] = betas[0, 1]
        V[13, 7] = betas[1, 0]
        V[13, 8] = betas[1, 1]

        # Now let's fix the scaling.
        h = coordinate_mapping.cell_size()

        # This gets the vertex gradients
        for v in range(3):
            for k in range(2):
                for i in range(15):
                    V[i, 3*v+1+k] = V[i, 3*v+1+k] / h[v]

        # this scales second derivative moments.  First should be ok.
        for e in range(3):
            v0id, v1id = [i for i in range(3) if i != e]
            for i in range(15):
                V[i, 12+e] = 2*V[i, 12+e] / (h[v0id] + h[v1id])

        return ListTensor(V.T)


class WuXuH3NC(PhysicallyMappedElement, ScalarFiatElement):
    def __init__(self, cell, degree=None):
        if degree is None:
            degree = 4
        if degree != 4:
            raise ValueError("Degree must be 4 for the Wu-Xu element")
        if Citations is not None:
            Citations().register("WuXu2019")
        super().__init__(WuXuH3NC_fiat(cell))

    def basis_transformation(self, coordinate_mapping):
        J = coordinate_mapping.jacobian_at([1/3, 1/3])
        J = numpy.array([[J[0, 0], J[0, 1]],
                         [J[1, 0], J[1, 1]]])
        [[dxdxhat, dxdyhat], [dydxhat, dydyhat]] = J

        Thetainv = numpy.array(
            [[dxdxhat*dxdxhat, Literal(2) * dxdxhat * dydxhat, dydxhat*dydxhat],
             [dxdyhat * dxdxhat, dxdyhat * dydxhat + dxdxhat * dydyhat, dydxhat * dydyhat],
             [dxdyhat*dxdyhat, Literal(2) * dxdyhat * dydyhat, dydyhat*dydyhat]])
        nhats = coordinate_mapping.reference_normals()
        ns = coordinate_mapping.physical_normals()

        ts = coordinate_mapping.physical_tangents()

        thats = numpy.zeros((3, 2), dtype=object)
        for e in range(3):
            tancur = self.cell.compute_normalized_edge_tangent(e)
            for i in range(2):
                thats[e, i] = Literal(tancur[i])

        lens = coordinate_mapping.physical_edge_lengths()

        V = numpy.zeros((12, 12), dtype=object)

        for multiindex in numpy.ndindex(V.shape):
            V[multiindex] = Literal(V[multiindex])

        Gs = numpy.zeros((3, 2, 2), dtype='O')
        Ghats = numpy.zeros((3, 2, 2), dtype='O')
        Gammas = numpy.zeros((3, 3, 3), dtype='O')
        Gammainvhats = numpy.zeros((3, 3, 3), dtype='O')
        B2s = numpy.zeros((3, 3, 3), dtype='O')
        betas = numpy.zeros((3, 2), dtype='O')

        for e in range(3):
            nx = ns[e, 0]
            ny = ns[e, 1]
            nhatx = nhats[e, 0]
            nhaty = nhats[e, 1]
            tx = ts[e, 0]
            ty = ts[e, 1]
            thatx = thats[e, 0]
            thaty = thats[e, 1]

            Gs[e, :, :] = numpy.asarray([[nx, ny], [tx, ty]])
            Ghats[e, :, :] = numpy.asarray([[nhatx, nhaty],
                                            [thatx, thaty]])

            Gammas[e, :, :] = numpy.asarray(
                [[nx*nx, Literal(2)*nx*tx, tx*tx],
                 [nx*ny, nx*ty+ny*tx, tx*ty],
                 [ny*ny, Literal(2)*ny*ty, ty*ty]])

            Gammainvhats[e, :, :] = numpy.asarray(
                [[nhatx*nhatx, Literal(2)*nhatx*nhaty, nhaty*nhaty],
                 [nhatx*thatx, nhatx*thaty+nhaty*thatx, nhaty*thaty],
                 [thatx*thatx, Literal(2)*thatx*thaty, thaty*thaty]])

            B2s[e, :, :] = numpy.dot(Gammainvhats[e],
                                     numpy.dot(Thetainv, Gammas[e]))# / lens[e]

            betas[e, 0] = (nx * B2s[e, 0, 1] + tx * B2s[e, 0, 2])/lens[e]
            betas[e, 1] = (ny * B2s[e, 0, 1] + ty * B2s[e, 0, 2])/lens[e]

        for e in range(3):
            V[3*e, 3*e] = Literal(1)
            for i in range(2):
                for j in range(2):
                    V[3*e+1+i, 3*e+1+j] = J[j, i]

        for e in range(9, 12):
            V[e, e] = B2s[e-9, 0, 0]

        V[9, 4] = Literal(-1) * betas[0, 0]
        V[9, 5] = Literal(-1) * betas[0, 1]
        V[9, 7] = betas[0, 0]
        V[9, 8] = betas[0, 1]
        V[10, 1] = Literal(-1) * betas[1, 0]
        V[10, 2] = Literal(-1) * betas[1, 1]
        V[10, 7] = betas[1, 0]
        V[10, 8] = betas[1, 1]
        V[11, 1] = Literal(-1) * betas[2, 0]
        V[11, 2] = Literal(-1) * betas[2, 1]
        V[11, 4] = betas[2, 0]
        V[11, 5] = betas[2, 1]        

        # Now let's fix the scaling.
        h = coordinate_mapping.cell_size()

        # This gets the vertex gradients
        for v in range(3):
            for k in range(2):
                for i in range(12):
                    V[i, 3*v+1+k] = V[i, 3*v+1+k] / h[v]

        # this scales second derivative moments.  First should be ok.
        for e in range(3):
            v0id, v1id = [i for i in range(3) if i != e]
            for i in range(12):
                V[i, 9+e] = 2*V[i, 9+e] / (h[v0id] + h[v1id])

        return ListTensor(V.T)
