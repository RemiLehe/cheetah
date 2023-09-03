import test.ARESlatticeStage3v1_9 as ares
from copy import deepcopy

import numpy as np
import ocelot

import cheetah


def test_dipole():
    """
    Test that the tracking results through a Cheeath `Dipole` element match those
    through an Oclet `Bend` element.
    """
    # Cheetah
    incoming_beam = cheetah.ParticleBeam.from_astra(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    cheetah_dipole = cheetah.Dipole(length=0.1, angle=0.1)
    outgoing_beam = cheetah_dipole.track(incoming_beam)

    # Ocelot
    incoming_p_array = ocelot.astraBeam2particleArray(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    ocelot_bend = ocelot.Bend(l=0.1, angle=0.1)
    lattice = ocelot.MagneticLattice([ocelot_bend])
    navigator = ocelot.Navigator(lattice)
    _, outgoing_p_array = ocelot.track(lattice, deepcopy(incoming_p_array), navigator)

    assert np.allclose(
        outgoing_beam.particles[:, :6], outgoing_p_array.rparticles.transpose()
    )


def test_dipole_with_fringe_field():
    """
    Test that the tracking results through a Cheeath `Dipole` element match those
    through an Oclet `Bend` element when there are fringe fields.
    """
    # Cheetah
    incoming_beam = cheetah.ParticleBeam.from_astra(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    cheetah_dipole = cheetah.Dipole(length=0.1, angle=0.1, fringe_integral=0.1, gap=0.2)
    outgoing_beam = cheetah_dipole.track(incoming_beam)

    # Ocelot
    incoming_p_array = ocelot.astraBeam2particleArray(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    ocelot_bend = ocelot.Bend(l=0.1, angle=0.1, fint=0.1, gap=0.2)
    lattice = ocelot.MagneticLattice([ocelot_bend])
    navigator = ocelot.Navigator(lattice)
    _, outgoing_p_array = ocelot.track(lattice, deepcopy(incoming_p_array), navigator)

    assert np.allclose(
        outgoing_beam.particles[:, :6], outgoing_p_array.rparticles.transpose()
    )


def test_aperture():
    """
    Test that the tracking results through a Cheeath `Aperture` element match those
    through an Oclet `Aperture` element.
    """
    # Cheetah
    incoming_beam = cheetah.ParticleBeam.from_astra(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    cheetah_segment = cheetah.Segment(
        [
            cheetah.Aperture(
                x_max=2e-4,
                y_max=2e-4,
                shape="rectangular",
                name="aperture",
                is_active=True,
            ),
            cheetah.Drift(length=0.1),
        ]
    )
    outgoing_beam = cheetah_segment.track(incoming_beam)

    # Ocelot
    incoming_p_array = ocelot.astraBeam2particleArray(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    ocelot_cell = [ocelot.Aperture(xmax=2e-4, ymax=2e-4), ocelot.Drift(l=0.1)]
    lattice = ocelot.MagneticLattice([ocelot_cell])
    navigator = ocelot.Navigator(lattice)
    navigator.activate_apertures()
    _, outgoing_p_array = ocelot.track(lattice, deepcopy(incoming_p_array), navigator)

    assert outgoing_beam.num_particles == outgoing_p_array.rparticles.shape[1]


def test_aperture_elliptical():
    """
    Test that the tracking results through an elliptical Cheeath `Aperture` element
    match those through an elliptical Oclet `Aperture` element.
    """
    # Cheetah
    incoming_beam = cheetah.ParticleBeam.from_astra(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    cheetah_segment = cheetah.Segment(
        [
            cheetah.Aperture(
                x_max=2e-4,
                y_max=2e-4,
                shape="elliptical",
                name="aperture",
                is_active=True,
            ),
            cheetah.Drift(length=0.1),
        ]
    )
    outgoing_beam = cheetah_segment.track(incoming_beam)

    # Ocelot
    incoming_p_array = ocelot.astraBeam2particleArray(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    ocelot_cell = [
        ocelot.Aperture(xmax=2e-4, ymax=2e-4, type="ellipt"),
        ocelot.Drift(l=0.1),
    ]
    lattice = ocelot.MagneticLattice([ocelot_cell])
    navigator = ocelot.Navigator(lattice)
    navigator.activate_apertures()
    _, outgoing_p_array = ocelot.track(lattice, deepcopy(incoming_p_array), navigator)

    assert outgoing_beam.num_particles == outgoing_p_array.rparticles.shape[1]


def test_solenoid():
    """
    Test that the tracking results through a Cheeath `Solenoid` element match those
    through an Oclet `Solenoid` element.
    """
    # Cheetah
    incoming_beam = cheetah.ParticleBeam.from_astra(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    cheetah_solenoid = cheetah.Solenoid(length=0.5, k=5)
    outgoing_beam = cheetah_solenoid.track(incoming_beam)

    # Ocelot
    incoming_p_array = ocelot.astraBeam2particleArray(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    ocelot_solenoid = ocelot.Solenoid(l=0.5, k=5)
    lattice = ocelot.MagneticLattice([ocelot_solenoid])
    navigator = ocelot.Navigator(lattice)
    _, outgoing_p_array = ocelot.track(lattice, deepcopy(incoming_p_array), navigator)

    assert np.allclose(
        outgoing_beam.particles[:, :6], outgoing_p_array.rparticles.transpose()
    )


def test_ares_ea():
    """
    Test that the tracking results through a Experimental Area (EA) lattice of the ARES
    accelerator at DESY match those using Ocelot.
    """
    cell = cheetah.utils.subcell_of_ocelot(ares.cell, "AREASOLA1", "AREABSCR1")
    ares.areamqzm1.k1 = 5.0
    ares.areamqzm2.k1 = -5.0
    ares.areamcvm1.k1 = 1e-3
    ares.areamqzm3.k1 = 5.0
    ares.areamchm1.k1 = -2e-3

    # Cheetah
    incoming_beam = cheetah.ParticleBeam.from_astra(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001"
    )
    cheetah_segment = cheetah.Segment.from_ocelot(cell)
    outgoing_beam = cheetah_segment.track(incoming_beam)

    # Ocelot
    incoming_p_array = ocelot.astraBeam2particleArray(
        "benchmark/cheetah/ACHIP_EA1_2021.1351.001", print_params=False
    )
    lattice = ocelot.MagneticLattice(cell)
    navigator = ocelot.Navigator(lattice)
    _, outgoing_p_array = ocelot.track(lattice, deepcopy(incoming_p_array), navigator)

    assert np.isclose(outgoing_beam.mu_x, outgoing_p_array.x().mean())
    assert np.isclose(outgoing_beam.mu_xp, outgoing_p_array.px().mean())
    assert np.isclose(outgoing_beam.mu_y, outgoing_p_array.y().mean())
    assert np.isclose(outgoing_beam.mu_yp, outgoing_p_array.py().mean())
    assert np.isclose(outgoing_beam.mu_s, outgoing_p_array.tau().mean(), atol=1e-7)
    assert np.isclose(outgoing_beam.mu_p, outgoing_p_array.p().mean())

    assert np.allclose(outgoing_beam.xs, outgoing_p_array.x())
    assert np.allclose(outgoing_beam.xps, outgoing_p_array.px())
    assert np.allclose(outgoing_beam.ys, outgoing_p_array.y())
    assert np.allclose(outgoing_beam.yps, outgoing_p_array.py())
    assert np.allclose(
        outgoing_beam.ss, outgoing_p_array.tau(), atol=1e-7, rtol=1e-1
    )  # TODO: Why do we need such large tolerances?
    assert np.allclose(outgoing_beam.ps, outgoing_p_array.p())
