import argparse
import math
import sys

import meshio
import meshplex
import numpy

from .. import cpt, cvt, laplace, odt
from ..__about__ import __version__


def _get_parser():
    parser = argparse.ArgumentParser(
        description="Mesh smoothing/optimization.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "input_file", metavar="INPUT_FILE", type=str, help="Input mesh file"
    )

    parser.add_argument(
        "output_file", metavar="OUTPUT_FILE", type=str, help="Output mesh file"
    )

    parser.add_argument(
        "--method",
        "-m",
        choices=[
            "laplace",
            "cpt-dp",
            "cpt-uniform-fp",
            "cpt-uniform-qn",
            #
            "lloyd",
            "cvt-uniform-fp",
            "cvt-uniform-qnb",
            "cvt-uniform-qnf",
            #
            "odt-dp-fp",
            "odt-uniform-fp",
            "odt-uniform-bfgs",
        ],
        default="cvt-uniform-qnf",
        help="smoothing method (default: cvt-uniform-qnf)",
    )

    parser.add_argument(
        "--omega",
        metavar="OMEGA",
        default=1.0,
        type=float,
        help="relaxation parameter (default: 1.0, no relaxation)",
    )

    parser.add_argument(
        "--max-num-steps",
        "-n",
        metavar="MAX_NUM_STEPS",
        type=int,
        default=math.inf,
        help="maximum number of steps (default: infinity)",
    )

    parser.add_argument(
        "--tolerance",
        "-t",
        metavar="TOL",
        default=1.0e-10,
        type=float,
        help="convergence criterion (method dependent, default: 1.0e-8)",
    )

    parser.add_argument(
        "--quiet",
        default=False,
        action="store_true",
        help="don't produce any output (default: false)",
    )

    parser.add_argument(
        "--step-filename-format",
        "-f",
        metavar="FMT",
        default=None,
        help=(
            "filename format for mesh at every step "
            "(e.g., `step{:3d}.vtk`, default: None)"
        ),
    )

    parser.add_argument(
        "--store-cell-quality",
        "-q",
        default=False,
        action="store_true",
        help=("store cell quality data in output files (default: False)"),
    )

    parser.add_argument(
        "--subdomain-field-name",
        "-s",
        metavar="SUBDOMAIN",
        default=None,
        help="name of the subdomain field in in the input file (default: None)",
    )

    version = "\n".join(
        [
            "optimesh {} [Python {}.{}.{}]".format(
                __version__,
                sys.version_info.major,
                sys.version_info.minor,
                sys.version_info.micro,
            ),
            "Copyright (C) 2018-2020 Nico Schlömer <nico.schloemer@gmail.com>",
        ]
    )

    parser.add_argument(
        "--version",
        "-v",
        help="display version information",
        action="version",
        version=version,
    )
    return parser


def prune(mesh):
    ncells = numpy.concatenate([numpy.concatenate(data) for _, data in mesh.cells])
    uvertices, uidx = numpy.unique(ncells, return_inverse=True)
    k = 0
    for cell_type, data in mesh.cells:
        n = numpy.prod(data.shape)
        data[:] = uidx[k : k + n].reshape(data.shape)
        k += n
    mesh.points = mesh.points[uvertices]
    for key in mesh.point_data:
        mesh.point_data[key] = mesh.point_data[key][uvertices]


def main(argv=None):
    parser = _get_parser()
    args = parser.parse_args(argv)

    if not (args.max_num_steps < math.inf or args.tolerance > 0.0):
        parser.error("At least one of --max-num-steps or --tolerance required.")

    mesh = meshio.read(args.input_file)

    # Remove all points which do not belong to the highest-order simplex. Those would
    # lead to singular equations systems further down the line.
    mesh.cells = [meshio.CellBlock("triangle", mesh.get_cells_type("triangle"))]
    prune(mesh)

    if args.subdomain_field_name:
        field = mesh.cell_data["triangle"][args.subdomain_field_name]
        subdomain_idx = numpy.unique(field)
        cell_sets = [idx == field for idx in subdomain_idx]
    else:
        cell_sets = [numpy.ones(mesh.get_cells_type("triangle").shape[0], dtype=bool)]

    method = {
        "laplace": laplace.fixed_point,
        #
        "cpt-dp": cpt.linear_solve_density_preserving,
        "cpt-uniform-fp": cpt.fixed_point_uniform,
        "cpt-uniform-qn": cpt.quasi_newton_uniform,
        #
        "lloyd": cvt.quasi_newton_uniform_lloyd,
        "cvt-uniform-fp": cvt.quasi_newton_uniform_lloyd,
        "cvt-uniform-qnb": cvt.quasi_newton_uniform_blocks,
        "cvt-uniform-qnf": cvt.quasi_newton_uniform_full,
        #
        "odt-dp-fp": odt.fixed_point_density_preserving,
        "odt-uniform-fp": odt.fixed_point_uniform,
        "odt-uniform-bfgs": odt.nonlinear_optimization_uniform,
    }[args.method]

    cells = mesh.get_cells_type("triangle")

    for cell_idx in cell_sets:
        if args.method in ["odt-uniform-bfgs"]:
            # no relaxation parameter omega
            X, cls = method(
                mesh.points,
                cells[cell_idx],
                args.tolerance,
                args.max_num_steps,
                verbose=~args.quiet,
                step_filename_format=args.step_filename_format,
            )
        else:
            X, cls = method(
                mesh.points,
                cells[cell_idx],
                args.tolerance,
                args.max_num_steps,
                omega=args.omega,
                verbose=~args.quiet,
                step_filename_format=args.step_filename_format,
            )

        cells[cell_idx] = cls

    q = meshplex.MeshTri(X, cls).q_radius_ratio
    meshio.write_points_cells(
        args.output_file,
        X,
        [("triangle", cells)],
        cell_data={"cell_quality": [q]},
    )
