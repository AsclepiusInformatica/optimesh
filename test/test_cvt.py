import meshplex
import numpy
import pytest
from scipy.spatial import Delaunay

import optimesh

from .helpers import assert_norm_equality
from .meshes import pacman, simple1


@pytest.mark.parametrize(
    "mesh, num_steps, ref",
    [
        (simple1, 1, [4.9319444444444445e00, 2.1063181153582713e00, 1.0]),
        (simple1, 100, [4.9863354526224510, 2.1181412069258942, 1.0]),
        # We're adding relatively many tests here. The reason is that even small changes
        # in meshplex, e.g., in the computation of the circumcenters, can build up
        # across a CVT iteration and lead to differences that aren't so small. The
        # sequence of tests is makes sure that the difference builds up step-by-step and
        # isn't a sudden break.
        (pacman, 1, [1.9449825885691200e03, 7.6122084669586002e01, 5.0]),
        (pacman, 2, [1.9446726479253102e03, 7.6115000143782524e01, 5.0]),
        (pacman, 10, [1.9424088268502351e03, 7.6063446601225976e01, 5.0]),
        (pacman, 20, [1.9407096235482659e03, 7.6028721177100564e01, 5.0]),
        (pacman, 30, [1.9397254043011189e03, 7.6011552957849773e01, 5.0]),
        (pacman, 40, [1.9391902386060749e03, 7.6005991941058554e01, 5.0]),
        (pacman, 50, [1.9387458681863050e03, 7.6000274907001128e01, 5.0]),
        (pacman, 75, [1.9382955586258918e03, 7.5996522104610762e01, 5.0]),
        (pacman, 100, [1.9378484402198492e03, 7.5989305418917112e01, 5.0]),
    ],
)
def test_cvt_lloyd(mesh, num_steps, ref):
    print(mesh)
    print(num_steps)
    X, cells = mesh()
    m = meshplex.MeshTri(X, cells)
    optimesh.optimize(m, "Lloyd", 1.0e-2, num_steps, verbose=False)
    assert_norm_equality(m.points, ref, 1.0e-15)

    # try the other way of calling optimesh
    X, c = mesh()
    X, _ = optimesh.optimize_points_cells(X, c, "lloyd", 1.0e-2, num_steps)
    assert_norm_equality(X, ref, 1.0e-15)


@pytest.mark.parametrize(
    "mesh, ref",
    [
        (simple1, [4.9959407761650168e00, 2.1203672449514870e00, 1.0]),
        (pacman, [1.9366904328888943e03, 7.5960601959936454e01, 5.0]),
    ],
)
def test_cvt_lloyd_overrelaxed(mesh, ref):
    X, cells = mesh()
    m = meshplex.MeshTri(X, cells)
    optimesh.optimize(m, "Lloyd", 1.0e-2, 100, omega=2.0)
    assert_norm_equality(m.points, ref, 1.0e-12)


@pytest.mark.parametrize(
    "mesh, ref",
    [
        (simple1, [4.9957677170205690e00, 2.1203267741647247e00, 1.0]),
        (pacman, [1.9368768318452251e03, 7.5956311677633323e01, 5.0]),
    ],
)
def test_cvt_qnb(mesh, ref):
    X, cells = mesh()
    m = meshplex.MeshTri(X, cells)
    optimesh.optimize(m, "CVT (block-diagonal)", 1.0e-2, 100)
    assert_norm_equality(m.points, ref, 1.0e-10)


def test_cvt_qnb_boundary(n=10):
    X, cells = create_random_circle(n=n, radius=1.0)

    def boundary_step(x):
        x0 = [0.0, 0.0]
        r = 1.0
        # simply project onto the circle
        y = (x.T - x0).T
        r = numpy.sqrt(numpy.einsum("ij,ij->j", y, y))
        return ((y / r * r).T + x0).T

    mesh = meshplex.MeshTri(X, cells)
    optimesh.optimize(mesh, "Lloyd", 1.0e-2, 100, boundary_step=boundary_step)

    # X, cells = optimesh.cvt.quasi_newton_uniform_lloyd(
    #     X, cells, 1.0e-2, 100, boundary_step=boundary_step
    # )
    # X, cells = optimesh.cvt.quasi_newton_uniform_blocks(
    #     X, cells, 1.0e-2, 100, boundary=Circle()
    # )

    mesh.show()

    # Assert that we're dealing with the mesh we expect.
    # assert_norm_equality(X, [ref1, ref2, refi], 1.0e-12)


@pytest.mark.parametrize(
    "mesh, ref",
    [
        (simple1, [4.9971490009329251e00, 2.1206501666066013e00, 1.0]),
        (pacman, [1.9381715572352605e03, 7.5986456190117352e01, 5.0]),
    ],
)
def test_cvt_qnf(mesh, ref):
    X, cells = mesh()
    X, cells = optimesh.optimize_points_cells(
        X, cells, "cvt (full)", 1.0e-2, 100, omega=0.9
    )

    import meshplex

    mesh = meshplex.MeshTri(X, cells)
    mesh.show()

    # Assert that we're dealing with the mesh we expect.
    assert_norm_equality(X, ref, 1.0e-12)


def create_random_circle(n, radius, seed=0):
    k = numpy.arange(n)
    boundary_pts = radius * numpy.column_stack(
        [numpy.cos(2 * numpy.pi * k / n), numpy.sin(2 * numpy.pi * k / n)]
    )

    # Compute the number of interior points such that all triangles can be somewhat
    # equilateral.
    edge_length = 2 * numpy.pi * radius / n
    domain_area = numpy.pi - n * (
        radius ** 2 / 2 * (edge_length - numpy.sin(edge_length))
    )
    cell_area = numpy.sqrt(3) / 4 * edge_length ** 2
    target_num_cells = domain_area / cell_area
    # Euler:
    # 2 * num_points - num_boundary_edges - 2 = num_cells
    # <=>
    # num_interior_points ~= 0.5 * (num_cells + num_boundary_edges) + 1 - num_boundary_points
    m = int(0.5 * (target_num_cells + n) + 1 - n)

    # Generate random points in circle;
    # <http://mathworld.wolfram.com/DiskPointPicking.html>.
    # Choose the seed such that the fully smoothened mesh has no random boundary points.
    if seed is not None:
        numpy.random.seed(seed)
    r = numpy.random.rand(m)
    alpha = 2 * numpy.pi * numpy.random.rand(m)

    interior_pts = numpy.column_stack(
        [numpy.sqrt(r) * numpy.cos(alpha), numpy.sqrt(r) * numpy.sin(alpha)]
    )

    pts = numpy.concatenate([boundary_pts, interior_pts])

    tri = Delaunay(pts)
    # pts = numpy.column_stack([pts[:, 0], pts[:, 1], numpy.zeros(pts.shape[0])])
    return pts, tri.simplices


# This test iterates over a few meshes that produce weird sitations that did have the
# methods choke. Mostly bugs in GhostedMesh.
@pytest.mark.parametrize("seed", [0, 4, 20])
def test_for_breakdown(seed):
    numpy.random.seed(seed)

    n = numpy.random.randint(10, 20)
    pts, cells = create_random_circle(n=n, radius=1.0)

    optimesh.optimize_points_cells(
        pts, cells, "lloyd", omega=1.0, tol=1.0e-10, max_num_steps=10
    )


if __name__ == "__main__":
    test_cvt_qnb_boundary(50)
