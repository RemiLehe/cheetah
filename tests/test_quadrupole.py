import torch

from cheetah import Drift, ParameterBeam, ParticleBeam, Quadrupole, Segment


def test_quadrupole_off():
    """
    Test that a quadrupole with k1=0 behaves still like a drift.
    """
    quadrupole = Quadrupole(length=torch.tensor([1.0]), k1=torch.tensor([0.0]))
    drift = Drift(length=torch.tensor([1.0]))
    incoming_beam = ParameterBeam.from_parameters(
        sigma_px=torch.tensor([2e-7]), sigma_py=torch.tensor([2e-7])
    )
    outbeam_quad = quadrupole(incoming_beam)
    outbeam_drift = drift(incoming_beam)

    quadrupole.k1 = torch.tensor([1.0], device=quadrupole.k1.device)
    outbeam_quad_on = quadrupole(incoming_beam)

    assert torch.allclose(outbeam_quad.sigma_x, outbeam_drift.sigma_x)
    assert not torch.allclose(outbeam_quad_on.sigma_x, outbeam_drift.sigma_x)


def test_quadrupole_with_misalignments_batched():
    """
    Test that a quadrupole with misalignments behaves as expected.
    """

    quad_with_misalignment = Quadrupole(
        length=torch.tensor([1.0]),
        k1=torch.tensor([1.0]),
        misalignment=torch.tensor([[0.1, 0.1]]),
    )

    assert quad_with_misalignment.batch_shape == torch.Size([1, 2])

    quad_without_misalignment = Quadrupole(
        length=torch.tensor([1.0]), k1=torch.tensor([1.0])
    )
    incoming_beam = ParameterBeam.from_parameters(
        sigma_px=torch.tensor([2e-7]), sigma_py=torch.tensor([2e-7])
    )
    outbeam_quad_with_misalignment = quad_with_misalignment(incoming_beam)
    outbeam_quad_without_misalignment = quad_without_misalignment(incoming_beam)

    assert not torch.allclose(
        outbeam_quad_with_misalignment.mu_x,
        outbeam_quad_without_misalignment.mu_x,
    )


def test_quadrupole_with_misalignments_multiple_batch_dimensions():
    """
    Test that a quadrupole with misalignments that have multiple batch dimensions does
    not raise an error and behaves as expected.
    """

    misalignments = torch.randn((4, 3, 2))
    quad_with_misalignment = Quadrupole(
        length=torch.tensor(1.0), k1=torch.tensor(1.0), misalignment=misalignments
    )

    quad_without_misalignment = Quadrupole(
        length=torch.tensor(1.0), k1=torch.tensor(1.0)
    )
    incoming_beam = ParameterBeam.from_parameters(
        sigma_px=torch.tensor(2e-7), sigma_py=torch.tensor(2e-7)
    )
    outbeam_quad_with_misalignment = quad_with_misalignment(incoming_beam)
    outbeam_quad_without_misalignment = quad_without_misalignment(incoming_beam)

    # Check that the misalignment has an effect
    assert not torch.allclose(
        outbeam_quad_with_misalignment.mu_x,
        outbeam_quad_without_misalignment.mu_x,
    )

    # Check that the output shape is correct
    assert outbeam_quad_with_misalignment.mu_x.shape == misalignments.shape[:-1]


def test_tilted_quadrupole_batch():
    """
    Test that a quadrupole with a multiple tilts behaves as expected.
    """
    incoming = ParticleBeam.from_parameters(
        num_particles=torch.tensor(1_000_000),
        energy=torch.tensor(1e9),
        mu_x=torch.tensor(1e-5),
    )
    segment = Segment(
        [
            Quadrupole(
                length=torch.tensor([0.5, 0.5, 0.5]),
                k1=torch.tensor([1.0, 1.0, 1.0]),
                tilt=torch.tensor([torch.pi / 4, torch.pi / 2, torch.pi * 5 / 4]),
            ),
            Drift(length=torch.tensor(0.5)),
        ]
    )
    outgoing = segment(incoming)

    # Check pi/4 and 5/4*pi rotations is the same for quadrupole
    assert torch.allclose(outgoing.particles[0], outgoing.particles[2])

    # Check pi/2 rotation is different
    assert not torch.allclose(outgoing.particles[0], outgoing.particles[1])


# TODO Change batched to vectorised
def test_tilted_quadrupole_multiple_batch_dimensions():
    """
    Test that a quadrupole with tilts that have multiple vectorisation dimensions does
    not raise an error and behaves as expected.
    """
    tilts = torch.tensor(
        [
            [torch.pi / 4, torch.pi / 2, torch.pi * 5 / 4],
            [torch.pi * 5 / 4, torch.pi / 2, torch.pi / 4],
        ]
    )
    segment = Segment(
        [
            Quadrupole(length=torch.tensor(0.5), k1=torch.tensor(1.0), tilt=tilts),
            Drift(length=torch.tensor(0.5)),
        ]
    )

    incoming = ParticleBeam.from_parameters(
        num_particles=torch.tensor(10_000),
        energy=torch.tensor(1e9),
        mu_x=torch.tensor(1e-5),
    )

    outgoing = segment(incoming)

    assert torch.allclose(
        outgoing.particles[0, 0], outgoing.particles[0, 1], rtol=1e-1, atol=1e-5
    )
    assert outgoing.particles.shape == (2, 3, 10_000, 7)


def test_quadrupole_length_multiple_batch_dimensions():
    """
    Test that a quadrupole with lengths that have multiple vectorisation dimensions does
    not raise an error and behaves as expected.
    """
    lengths = torch.tensor([[0.2, 0.3, 0.4], [0.5, 0.6, 0.7]])
    segment = Segment(
        [
            Quadrupole(length=lengths, k1=torch.tensor(4.2)),
            Drift(length=lengths * 2),
        ]
    )

    incoming = ParticleBeam.from_parameters(
        num_particles=torch.tensor(10_000),
        energy=torch.tensor(1e9),
        mu_x=torch.tensor(1e-5),
    )

    outgoing = segment(incoming)

    assert outgoing.particles.shape == (2, 3, 10_000, 7)
