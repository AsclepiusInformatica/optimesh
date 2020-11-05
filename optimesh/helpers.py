import numpy
import termplotlib as tpl


def print_stats(mesh, extra_cols=None):
    extra_cols = [] if extra_cols is None else extra_cols

    angles = mesh.angles / numpy.pi * 180
    angles_hist, angles_bin_edges = numpy.histogram(
        angles, bins=numpy.linspace(0.0, 180.0, num=73, endpoint=True)
    )

    q = mesh.cell_quality
    q_hist, q_bin_edges = numpy.histogram(
        q, bins=numpy.linspace(0.0, 1.0, num=41, endpoint=True)
    )

    grid = tpl.subplot_grid(
        (1, 4 + len(extra_cols)), column_widths=None, border_style=None
    )
    grid[0, 0].hist(angles_hist, angles_bin_edges, grid=[24], bar_width=1, strip=True)
    grid[0, 1].aprint("min angle:     {:7.3f}".format(numpy.min(angles)))
    grid[0, 1].aprint("avg angle:     {:7.3f}".format(60))
    grid[0, 1].aprint("max angle:     {:7.3f}".format(numpy.max(angles)))
    grid[0, 1].aprint("std dev angle: {:7.3f}".format(numpy.std(angles)))
    grid[0, 2].hist(q_hist, q_bin_edges, bar_width=1, strip=True)
    grid[0, 3].aprint("min quality: {:5.3f}".format(numpy.min(q)))
    grid[0, 3].aprint("avg quality: {:5.3f}".format(numpy.average(q)))
    grid[0, 3].aprint("max quality: {:5.3f}".format(numpy.max(q)))

    for k, col in enumerate(extra_cols):
        grid[0, 4 + k].aprint(col)

    grid.show()


# def stepsize_till_flat(x, v):
#     """Given triangles and directions, compute the minimum stepsize t at which the area
#     of at least one of the new triangles `x + t*v` is zero.
#     """
#     # <https://math.stackexchange.com/a/3242740/36678>
#     x1x0 = x[:, 1] - x[:, 0]
#     x2x0 = x[:, 2] - x[:, 0]
#     #
#     v1v0 = v[:, 1] - v[:, 0]
#     v2v0 = v[:, 2] - v[:, 0]
#     #
#     a = v1v0[:, 0] * v2v0[:, 1] - v1v0[:, 1] * v2v0[:, 0]
#     b = (
#         v1v0[:, 0] * x2x0[:, 1]
#         + x1x0[:, 0] * v2v0[:, 1]
#         - v1v0[:, 1] * x2x0[:, 0]
#         - x1x0[:, 1] * v2v0[:, 0]
#     )
#     c = x1x0[:, 0] * x2x0[:, 1] - x1x0[:, 1] * x2x0[:, 0]
#     #
#     alpha = b ** 2 - 4 * a * c
#     i = (alpha >= 0) & (a != 0.0)
#     sqrt_alpha = numpy.sqrt(alpha[i])
#     t0 = (-b[i] + sqrt_alpha) / (2 * a[i])
#     t1 = (-b[i] - sqrt_alpha) / (2 * a[i])
#     return min(numpy.min(t0[t0 > 0]), numpy.min(t1[t1 > 0]))


def runner(
    get_new_points,
    mesh,
    tol,
    max_num_steps,
    omega=1.0,
    method_name=None,
    verbose=False,
    callback=None,
    step_filename_format=None,
    uniform_density=False,
    implicit_surface=None,
    implicit_surface_tol=1.0e-10,
):
    k = 0

    if verbose:
        print("\nBefore:")
        print_stats(mesh)
    if step_filename_format:
        mesh.save(
            step_filename_format.format(k),
            show_coedges=False,
            show_axes=False,
            cell_quality_coloring=("viridis", 0.0, 1.0, False),
        )

    if callback:
        callback(k, mesh)

    # mesh.write("out0.vtk")
    mesh.flip_until_delaunay()
    # mesh.write("out1.vtk")

    while True:
        k += 1

        new_points = get_new_points(mesh)
        diff = omega * (new_points - mesh.points)

        # Some methods are stable (CPT), others can break down if the mesh isn't very
        # smooth. A break-down manifests, for example, in a step size that lets
        # triangles become fully flat or even "overshoot". After that, anything can
        # happen. To prevent this, restrict the maximum step size to half of the minimum
        # the incircle radius of all adjacent cells. This makes sure that triangles
        # cannot "flip".
        # <https://stackoverflow.com/a/57261082/353337>
        max_step = numpy.full(mesh.points.shape[0], numpy.inf)
        numpy.minimum.at(
            max_step,
            mesh.cells["points"].reshape(-1),
            numpy.repeat(mesh.cell_inradius, 3),
        )
        max_step *= 0.5

        step_lengths = numpy.sqrt(numpy.einsum("ij,ij->i", diff, diff))
        # alpha = numpy.min(max_step / step_lengths)
        # alpha = numpy.min([alpha, 1.0])
        # diff *= alpha
        idx = step_lengths > max_step
        diff[idx] *= max_step[idx, None] / step_lengths[idx, None]

        mesh.points += diff

        # project all points back to the surface
        if implicit_surface is not None:
            fval = implicit_surface.f(mesh.points.T)
            while numpy.any(numpy.abs(fval) > implicit_surface_tol):
                grad = implicit_surface.grad(mesh.points.T)
                grad_dot_grad = numpy.einsum("ij,ij->j", grad, grad)
                # The step is chosen in the direction of the gradient with a step size
                # such that, if the function was linear, the boundary (fval=0) would be
                # hit in one step.
                mesh.points -= (grad * (fval / grad_dot_grad)).T
                # compute new value
                fval = implicit_surface.f(mesh.points.T)

        mesh.update_values()
        mesh.flip_until_delaunay()
        # mesh.show(control_volume_centroid_color="C1")
        # mesh.show()

        # Abort the loop if the update was small
        diff_norm_2 = numpy.einsum("ij,ij->i", diff, diff)
        is_final = numpy.all(diff_norm_2 < tol ** 2) or k >= max_num_steps

        if is_final or step_filename_format:
            if is_final:
                info = "{} steps".format(k)
                if method_name is not None:
                    if abs(omega - 1.0) > 1.0e-10:
                        method_name += ", relaxation parameter {}".format(omega)
                    info += " of " + method_name

                if verbose:
                    print("\nFinal ({}):".format(info))
                    print_stats(mesh)
            if step_filename_format:
                mesh.save(
                    step_filename_format.format(k),
                    show_coedges=False,
                    show_axes=False,
                    cell_quality_coloring=("viridis", 0.0, 1.0, False),
                )
        if callback:
            callback(k, mesh)

        if is_final:
            break

    return k, numpy.max(numpy.sqrt(diff_norm_2))


def get_new_points_averaged(mesh, reference_points, weights=None):
    """Provided reference points for each cell (e.g., the barycenter), for each point
    this method returns the (weighted) average of the reference points of all adjacent
    cells. The weights could for example be the volumes of the cells.
    """
    if weights is None:
        scaled_rp = reference_points.T
    else:
        scaled_rp = reference_points.T * weights

    # new_points = numpy.zeros(mesh.points.shape)
    # for i in mesh.cells["points"].T:
    #     numpy.add.at(new_points, i, scaled_rp)
    # omega = numpy.zeros(len(mesh.points))
    # for i in mesh.cells["points"].T:
    #     numpy.add.at(omega, i, mesh.cell_volumes)

    n = mesh.points.shape[0]
    new_points = numpy.zeros(mesh.points.shape)
    for i in mesh.cells["points"].T:
        new_points += numpy.array(
            [numpy.bincount(i, vals, minlength=n) for vals in scaled_rp]
        ).T

    if weights is None:
        omega = numpy.bincount(mesh.cells["points"].reshape(-1), minlength=n)
    else:
        omega = numpy.zeros(n)
        for i in mesh.cells["points"].T:
            omega += numpy.bincount(i, weights, minlength=n)

    new_points /= omega[:, None]
    return new_points
