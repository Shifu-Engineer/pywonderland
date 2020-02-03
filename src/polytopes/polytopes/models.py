# -*- coding: utf-8 -*-
"""
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Classes for building models of 3D/4D polytopes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See the doc: "https://neozhaoliang.github.io/polytopes/"

"""
from itertools import combinations
import numpy as np
from . import helpers
from .todd_coxeter import CosetTable
from .povray import export_polytope_data


class BasePolytope(object):

    """
    Base class for building uniform polytopes using Wythoff's construction.
    """

    def __init__(self, coxeter_diagram, init_dist, extra_relations=()):
        """
        :param coxeter_diagram: Coxeter diagram for this polytope.
        :param init_dist: distances between the initial vertex and the mirrors.
        :param extra_relations: a presentation of a star polytope can be
            obtained by imposing more relations on the generators.
            For example "(ρ0ρ1ρ2ρ1)^n = 1" for some integer n, where n is the
            number of sides of a hole. See Coxeter's article

                "Regular skew polyhedra in three and four dimensions,
                 and their topological analogues"

        """
        # Coxeter matrix of the symmetry group
        self.coxeter_matrix = helpers.get_coxeter_matrix(coxeter_diagram)

        # reflectiom mirrors stored as row vectors in a matrix
        self.mirrors = helpers.get_mirrors(coxeter_diagram)

        # reflection transformations about the mirrors
        self.reflections = tuple(helpers.reflection_matrix(v) for v in self.mirrors)

        # the initial vertex
        self.init_v = helpers.get_init_point(self.mirrors, init_dist)

        # a mirror is active if and only if the initial vertex has non-zero distance to it
        self.active = tuple(bool(x) for x in init_dist)

        # generators of the symmetry group
        self.symmetry_gens = tuple(range(len(self.coxeter_matrix)))

        # relations between the generators
        self.symmetry_rels = tuple((i, j) * self.coxeter_matrix[i][j]
                                   for i, j in combinations(self.symmetry_gens, 2))
        # add the extra relations between generators (only used for star polytopes)
        self.symmetry_rels += tuple(extra_relations)

        # multiplication table bwteween the vertices
        self.vtable = None

        # number of vertices, edges, faces
        self.num_vertices = 0
        self.num_edges = 0
        self.num_faces = 0

        # coordinates of the vertices, indices of the edges and faces
        self.vertices_coords = []
        self.edge_indices = []
        self.face_indices = []

    def build_geometry(self):
        self.get_vertices()
        self.get_edges()
        self.get_faces()

    def get_vertices(self):
        """
        This method computes the following data that will be needed later:

        1. a coset table for the vertices.
        2. a complete list of word representations of the vertices.
        3. coordinates of the vertices.
        """
        # generators of the stabilizing subgroup that fixes the initial vertex.
        vgens = [(i,) for i, active in enumerate(self.active) if not active]
        self.vtable = CosetTable(self.symmetry_gens, self.symmetry_rels, vgens)
        self.vtable.run()
        # word representations of the vertices
        self.vwords = self.vtable.get_words()
        self.num_vertices = len(self.vwords)
        # apply words of the vertices to the initial vertex to get all vertices
        self.vertices_coords = tuple(self.transform(self.init_v, w) for w in self.vwords)

    def get_edges(self):
        """
        This method computes the indices of all edges.

        1. if the initial vertex lies on the i-th mirror then the
           reflection about this mirror fixes v0 and there are no
           edges of type i.

        2. else v0 and its virtual image v1 about this mirror generate
           a base edge e, the stabilizing subgroup of e is generated by
           the simple reflection ρi plus those simple reflections ρj such
           that ρj fixes v0 and commutes with ρi: ρiρj=ρjρi.
           Again we use Todd-Coxeter's procedure to get a complete list of
           word representations for the edges of type i and applyt them to
           e to get all edges of type i.
        """
        for i, active in enumerate(self.active):
            # if there are edges of type i
            if active:
                # generators of the edge stabilizing subgroup,
                # this is a standard parabolic subgroup generated by
                # the simple reflection ρi plus those simple reflections
                # ρj such that ρj fixes v0 and commutes with ρi.
                egens = [(i,)] + self.get_orthogonal_stabilizing_mirrors((i,))
                etable = CosetTable(self.symmetry_gens, self.symmetry_rels, egens)
                etable.run()
                # get word representations of the edges
                words = etable.get_words()
                elist = []
                # apply them to the base edge to get all edges of type i
                for word in words:
                    v1 = self.move(0, word)
                    v2 = self.move(0, (i,) + word)
                    elist.append((v1, v2))

                self.edge_indices.append(elist)
                self.num_edges += len(elist)

    def get_faces(self):
        """
        This method computes the indices of all faces.

        The composition of the i-th and the j-th reflection is a
        rotation which fixes a base face f. The stabilizing subgroup
        of f is generated by {ρi, ρj} plus those simple reflections
        ρk such that ρk fixes the initial vertex v0 and commutes with
        both ρi and ρj.
        """
        for i, j in combinations(self.symmetry_gens, 2):
            f0 = []
            m = self.coxeter_matrix[i][j]
            # generators of the face stabilizing subgroup
            fgens = [(i,), (j,)] + self.get_orthogonal_stabilizing_mirrors([i, j])

            # if both two mirrors are active then they generate a face
            if self.active[i] and self.active[j]:
                for k in range(m):
                    # rotate the base edge m times to get the base f,
                    # where m = self.coxeter_matrix[i][j]
                    f0.append(self.move(0, (i, j) * k))
                    f0.append(self.move(0, (j,) + (i, j) * k))

            # if exactly one of the two mirrors are active then they
            # generate a face only when they are not perpendicular
            elif (self.active[i] or self.active[j]) and m > 2:
                for k in range(m):
                    f0.append(self.move(0, (i, j) * k))

            # else they do not generate a face
            else:
                continue

            ftable = CosetTable(self.symmetry_gens, self.symmetry_rels, fgens)
            ftable.run()
            words = ftable.get_words()
            flist = []
            # apply the coset representatives to the base face to
            # get all faces of type (i, j)
            for word in words:
                f = tuple(self.move(v, word) for v in f0)
                flist.append(f)

            self.face_indices.append(flist)
            self.num_faces += len(flist)

    def transform(self, vector, word):
        """
        Transform a vector by a word in the symmetry group.
        Return the coordinates of the resulting vector.
        """
        for w in word:
            vector = np.dot(vector, self.reflections[w])
        return vector

    def move(self, vertex, word):
        """
        Transform a vertex by a word in the symmetry group.
        Return the index of the resulting vertex.
        """
        for w in word:
            vertex = self.vtable[vertex][w]
        return vertex

    def get_orthogonal_stabilizing_mirrors(self, subgens):
        """
        :param subgens: a list of generators, e.g. [0, 1]

        Given a list of generators in `subgens`, return the generators that
        commute with all of those in `subgens` and fix the initial vertex.
        """
        result = []
        for s in self.symmetry_gens:
            # check commutativity
            if all(self.coxeter_matrix[x][s] == 2 for x in subgens):
                # check if it fixes v0
                if not self.active[s]:
                    result.append((s,))
        return result

    def get_latex_format(self, symbol=r"\rho", cols=3, snub=False):
        """
        Return the words of the vertices in latex format.
        `cols` is the number of columns of the output latex array.
        """
        def to_latex(word):
            if not word:
                return "e"
            else:
                if snub:
                    return "".join(symbol + "_{{{}}}".format(i // 2) for i in word)
                else:
                    return "".join(symbol + "_{{{}}}".format(i) for i in word)

        latex = ""
        for i, word in enumerate(self.vwords):
            if i > 0 and i % cols == 0:
                latex += r"\\"
            latex += to_latex(word)
            if i % cols != cols - 1:
                latex += "&"

        return r"\begin{{array}}{{{}}}{}\end{{array}}".format("l" * cols, latex)

    def get_povray_data(self):
        return export_polytope_data(self)


class Polyhedra(BasePolytope):
    """
    Base class for 3d polyhedron.
    """

    def __init__(self, coxeter_diagram, init_dist, extra_relations=()):
        if not len(coxeter_diagram) == len(init_dist) == 3:
            raise ValueError("Length error: the inputs must all have length 3")
        super().__init__(coxeter_diagram, init_dist, extra_relations)


class Snub(Polyhedra):
    """
    A snub polyhedra is generated by the subgroup that consists of only
    rotations in the full symmetry group. This subgroup has presentation

        <r, s | r^p = s^q = (rs)^2 = 1>

    where r = ρ0ρ1, s = ρ1ρ2 are two rotations.
    Again we solve all words in this subgroup and then use them to
    transform the initial vertex to get all vertices.
    """

    def __init__(self, coxeter_diagram, init_dist=(1.0, 1.0, 1.0)):
        super().__init__(coxeter_diagram, init_dist, extra_relations=())
        # the representaion is not in the form of a Coxeter group,
        # we must overwrite the relations.

        # four generators (r, r^-1, s, s^-1)
        self.symmetry_gens = (0, 1, 2, 3)

        # relations in order:
        # 1. r^p = 1
        # 2. s^q = 1
        # 3. (rs)^2 = 1
        # 4. rr^-1 = 1
        # 5. ss^-1 = 1
        self.symmetry_rels = ((0,) * self.coxeter_matrix[0][1],
                              (2,) * self.coxeter_matrix[1][2],
                              (0, 2) * self.coxeter_matrix[0][2],
                              (0, 1), (2, 3))

        # order of the generator rotations {rotation: order}
        # {r: p, s: q, rs: 2}
        self.rotations = {(0,): self.coxeter_matrix[0][1],
                          (2,): self.coxeter_matrix[1][2],
                          (0, 2): self.coxeter_matrix[0][2]}

    def get_vertices(self):
        """
        Get the vertices of this snub polyhedra.
        """
        # the stabilizing subgroup of the initial vertex contains only 1
        self.vtable = CosetTable(self.symmetry_gens, self.symmetry_rels, coxeter=False)
        self.vtable.run()
        self.vwords = self.vtable.get_words()
        self.num_vertices = len(self.vwords)
        self.vertices_coords = tuple(self.transform(self.init_v, w) for w in self.vwords)

    def get_edges(self):
        """
        Get the edge indices of this snub polyhedra.
        Each rotation of the three "fundamental rotations" {r, s, rs} generates
        a base edge e, the stabilizing subgroup of e is <1> except that this
        rotation has order 2, i.e. a rotation generated by two commuting reflections.
        In this case the stabilizing subgroup is the cyclic group <rot> of order 2.
        """
        for rot in self.rotations:
            # if this rotation has order 2, then the edge stabilizing subgroup
            # is the cyclic subgroup <rot>
            if self.rotations[rot] == 2:
                egens = (rot,)
                etable = CosetTable(self.symmetry_gens, self.symmetry_rels, egens, coxeter=False)
                etable.run()
                words = etable.get_words()
            # else the edge stabilizing subgroup is <1>
            else:
                words = self.vwords

            elist = []
            e0 = (0, self.move(0, rot))  # the base edge
            # apply coset representatives to e0 to get all edges
            for word in words:
                e = tuple(self.move(v, word) for v in e0)
                elist.append(e)

            self.edge_indices.append(elist)
            self.num_edges += len(elist)

    def get_faces(self):
        """
        Get the face indices of this snub polyhedra.
        Each rotation of the three "fundamental rotations" {r, s, rs}
        generates a base face f0 if the order of this rotation is strictly
        greater than two, else it only gives an edge (degenerated face).

        There's another type of face given by the relation r*s = rs:
        it's generated by the three vertices {v0, v0s, v0rs}.
        Note (v0, v0s) is an edge of type s, (v0, v0rs) is an edge of type rs,
        (v0s, v0rs) is an edge of type r since it's in the same orbit of the
        edge (v0, v0r) by applying s on it.
        """
        for rot, order in self.rotations.items():
            # if the order of this rotation is > 2 then it generates a face
            if order > 2:
                flist = []
                # the vertices of this face are simply rotating the
                # initial vertex k times for k = 0, 1, ..., order.
                f0 = tuple(self.move(0, rot * k) for k in range(order))
                # the stabilizing group is the cyclic group <rot>
                fgens = (rot,)
                ftable = CosetTable(self.symmetry_gens, self.symmetry_rels, fgens, coxeter=False)
                ftable.run()
                words = ftable.get_words()
                for word in words:
                    f = tuple(self.move(v, word) for v in f0)
                    flist.append(f)

                self.face_indices.append(flist)
                self.num_faces += len(flist)

        # handle the special triangle face (v0, v0s, v0rs)
        # note its three edges are in different orbits so
        # its stabilizing subgroup must be <1>.
        triangle = (0, self.move(0, (2,)), self.move(0, (0, 2)))
        flist = []
        for word in self.vwords:
            f = tuple(self.move(v, word) for v in triangle)
            flist.append(f)

        self.face_indices.append(flist)
        self.num_faces += len(flist)

    def transform(self, vertex, word):
        """
        Transform a vertex by a word in the group.
        Return the coordinates of the resulting vertex.
        Note generator 0 means r = ρ0ρ1, generator 1 means s = ρ1ρ2.
        """
        for g in word:
            if g == 0:
                vertex = np.dot(vertex, self.reflections[0])
                vertex = np.dot(vertex, self.reflections[1])
            else:
                vertex = np.dot(vertex, self.reflections[1])
                vertex = np.dot(vertex, self.reflections[2])
        return vertex


class Polychora(BasePolytope):

    """
    Base class for 4d polychoron.
    """

    def __init__(self, coxeter_diagram, init_dist, extra_relations=()):
        if not (len(coxeter_diagram) == 6 and len(init_dist) == 4):
            raise ValueError("Length error: the input coxeter_diagram must have length 6 and init_dist has length 4")
        super().__init__(coxeter_diagram, init_dist, extra_relations)


class Polytope5D(BasePolytope):

    """
    Base class for 5d uniform polytopes.
    """

    def __init__(self, coxeter_diagram, init_dist, extra_relations=()):
        if len(coxeter_diagram) != 10 and len(init_dist) != 5:
            raise ValueError("Length error: the input coxeter_diagram must have length 10 and init_dist has length 5")
        super().__init__(coxeter_diagram, init_dist, extra_relations)

    def proj4d(self, pole=1.3):
        """
        Stereographic project vertices to 4d.
        """
        self.vertices_coords = [v[:4] / (1.3 - v[-1]) for v in self.vertices_coords]
        return self


class Snub24Cell(Polychora):

    """
    The snub 24-cell can be constructed from snub demitesseract [3^(1,1,1)]+,
    the procedure is similar with snub polyhedron above.
    Its symmetric group is generated by three rotations {r, s, t},
    a presentation is

           G = <r, s, t | r^3 = s^3 = t^3 = (rs)^2 = (rt)^2 = (s^-1 t)^2 = 1>

    where r = ρ0ρ1, s = ρ1ρ2, t = ρ1ρ3.
    """

    def __init__(self):
        coxeter_diagram = (3, 2, 2, 3, 3, 2)
        active = (1, 1, 1, 1)
        super().__init__(coxeter_diagram, active, extra_relations=())
        # generators in order: {r, r^-1, s, s^-1, t, t^-1}
        self.symmetry_gens = tuple(range(6))
        # relations in order:
        # 1. r^3 = 1
        # 2. s^3 = 1
        # 3. t^3 = 1
        # 4. (rs)^2 = 1
        # 5. (rt)^2 = 1
        # 6. (s^-1t)^2 = 1
        # 7. rr^-1 = 1
        # 8. ss^-1 = 1
        # 9. tt^-1 = 1
        self.symmetry_rels = ((0,) * 3, (2,) * 3, (4,) * 3,
                              (0, 2) * 2, (0, 4) * 2, (3, 4) * 2,
                              (0, 1), (2, 3), (4, 5))
        # rotations and their order
        # {r: 3, s: 3, t: 3, rs: 2, rt: 2, s^-1t: 2}
        self.rotations = {(0,): 3,
                          (2,): 3,
                          (4,): 3,
                          (0, 2): 2,
                          (0, 4): 2,
                          (3, 4): 2}

    def get_vertices(self):
        """
        Get the coordinates of the snub 24-cell.
        """
        self.vtable = CosetTable(self.symmetry_gens, self.symmetry_rels, coxeter=False)
        self.vtable.run()
        self.vwords = self.vtable.get_words()
        self.num_vertices = len(self.vwords)
        self.vertices_coords = tuple(self.transform(self.init_v, w) for w in self.vwords)

    def get_edges(self):
        """
        Get the edges of the snub 24-cell. Again each fundamental rotation
        in {r, s, t, rs, rt, s^-1t} generates edges of its type.
        """
        for rot, order in self.rotations.items():
            # if the rotation has order 2 then the edge stabilizing subgroup
            # is the cyclic subgroup <rot>, else it's <1>.
            if order == 2:
                egens = (rot,)
                etable = CosetTable(self.symmetry_gens, self.symmetry_rels, egens, coxeter=False)
                etable.run()
                words = etable.get_words()
            else:
                words = self.vwords

            elist = []
            e0 = (0, self.move(0, rot))
            for word in words:
                e = tuple(self.move(v, word) for v in e0)
                elist.append(e)

            self.edge_indices.append(elist)
            self.num_edges += len(elist)

    def get_faces(self):
        """
        Get the faces of the snub 24-cell.

        A fundamental rotation generates a face by rotating the initial
        vertex k times. This face is non-degenerate if and only if the
        order of the rotation is strictly greater than two. So only {r, s, t}
        can give faces of such type.

        There are also some triangle faces generated by relations like
        r1r2 = r3, where r1, r2, r3 are three fundamental rotations.
        """
        for rot in ((0,), (2,), (4,)):
            order = self.rotations[rot]
            flist = []
            f0 = tuple(self.move(0, rot * k) for k in range(order))
            fgens = (rot,)
            ftable = CosetTable(self.symmetry_gens, self.symmetry_rels, fgens, coxeter=False)
            ftable.run()
            words = ftable.get_words()
            for word in words:
                f = tuple(self.move(v, word) for v in f0)
                flist.append(f)

            self.face_indices.append(flist)
            self.num_faces += len(flist)

        # handle the special triangle faces generated from
        # 1. {v0, v0s, v0rs}
        # 2. {v0, v0t, v0rt},
        # 3. {v0, v0s, v0t^-1s}
        # 4. {v0, v0rs, v0t^-1s}
        # the edges of these triangles are in different orbits
        # hence their stabilizing subgroups are all <1>.
        for triangle in [(0, self.move(0, (2,)), self.move(0, (0, 2))),
                         (0, self.move(0, (4,)), self.move(0, (0, 4))),
                         (0, self.move(0, (2,)), self.move(0, (5, 2))),
                         (0, self.move(0, (0, 2)), self.move(0, (5, 2)))]:
            flist = []
            for word in self.vwords:
                f = tuple(self.move(v, word) for v in triangle)
                flist.append(f)

            self.face_indices.append(flist)
            self.num_faces += len(flist)

    def transform(self, vertex, word):
        for g in word:
            if g == 0:
                vertex = np.dot(vertex, self.reflections[0])
                vertex = np.dot(vertex, self.reflections[1])
            elif g == 2:
                vertex = np.dot(vertex, self.reflections[1])
                vertex = np.dot(vertex, self.reflections[2])
            else:
                vertex = np.dot(vertex, self.reflections[1])
                vertex = np.dot(vertex, self.reflections[3])
        return vertex
