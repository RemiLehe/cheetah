import numpy as np
import torch

from cheetah import ParticleBeam


def test_create_from_parameters():
    """
    Test that a `ParticleBeam` created from parameters actually has those parameters.
    """
    beam = ParticleBeam.from_parameters(
        num_particles=torch.tensor([1_000_000]),
        mu_x=torch.tensor([1e-5]),
        mu_xp=torch.tensor([1e-7]),
        mu_y=torch.tensor([2e-5]),
        mu_yp=torch.tensor([2e-7]),
        sigma_x=torch.tensor([1.75e-7]),
        sigma_xp=torch.tensor([2e-7]),
        sigma_y=torch.tensor([1.75e-7]),
        sigma_yp=torch.tensor([2e-7]),
        sigma_s=torch.tensor([0.000001]),
        sigma_p=torch.tensor([0.000001]),
        cor_x=torch.tensor([0.0]),
        cor_y=torch.tensor([0.0]),
        cor_s=torch.tensor([0.0]),
        energy=torch.tensor([1e7]),
        total_charge=torch.tensor([1e-9]),
    )

    assert beam.num_particles == 1_000_000
    assert np.isclose(beam.mu_x.cpu().numpy(), 1e-5)
    assert np.isclose(beam.mu_xp.cpu().numpy(), 1e-7)
    assert np.isclose(beam.mu_y.cpu().numpy(), 2e-5)
    assert np.isclose(beam.mu_yp.cpu().numpy(), 2e-7)
    assert np.isclose(beam.sigma_x.cpu().numpy(), 1.75e-7)
    assert np.isclose(beam.sigma_xp.cpu().numpy(), 2e-7)
    assert np.isclose(beam.sigma_y.cpu().numpy(), 1.75e-7)
    assert np.isclose(beam.sigma_yp.cpu().numpy(), 2e-7)
    assert np.isclose(beam.sigma_s.cpu().numpy(), 0.000001)
    assert np.isclose(beam.sigma_p.cpu().numpy(), 0.000001)
    assert np.isclose(beam.energy.cpu().numpy(), 1e7)
    assert np.isclose(beam.total_charge.cpu().numpy(), 1e-9)


def test_transform_to():
    """
    Test that a `ParticleBeam` transformed to new parameters actually has those new
    parameters.
    """
    original_beam = ParticleBeam.from_parameters()
    transformed_beam = original_beam.transformed_to(
        mu_x=torch.tensor([1e-5]),
        mu_xp=torch.tensor([1e-7]),
        mu_y=torch.tensor([2e-5]),
        mu_yp=torch.tensor([2e-7]),
        sigma_x=torch.tensor([1.75e-7]),
        sigma_xp=torch.tensor([2e-7]),
        sigma_y=torch.tensor([1.75e-7]),
        sigma_yp=torch.tensor([2e-7]),
        sigma_s=torch.tensor([0.000001]),
        sigma_p=torch.tensor([0.000001]),
        energy=torch.tensor([1e7]),
        total_charge=torch.tensor([1e-9]),
    )

    assert isinstance(transformed_beam, ParticleBeam)
    assert original_beam.num_particles == transformed_beam.num_particles

    assert np.isclose(transformed_beam.mu_x.cpu().numpy(), 1e-5)
    assert np.isclose(transformed_beam.mu_xp.cpu().numpy(), 1e-7)
    assert np.isclose(transformed_beam.mu_y.cpu().numpy(), 2e-5)
    assert np.isclose(transformed_beam.mu_yp.cpu().numpy(), 2e-7)
    assert np.isclose(transformed_beam.sigma_x.cpu().numpy(), 1.75e-7)
    assert np.isclose(transformed_beam.sigma_xp.cpu().numpy(), 2e-7)
    assert np.isclose(transformed_beam.sigma_y.cpu().numpy(), 1.75e-7)
    assert np.isclose(transformed_beam.sigma_yp.cpu().numpy(), 2e-7)
    assert np.isclose(transformed_beam.sigma_s.cpu().numpy(), 0.000001)
    assert np.isclose(transformed_beam.sigma_p.cpu().numpy(), 0.000001)
    assert np.isclose(transformed_beam.energy.cpu().numpy(), 1e7)
    assert np.isclose(transformed_beam.total_charge.cpu().numpy(), 1e-9)


def test_from_twiss_to_twiss():
    """
    Test that a `ParameterBeam` created from twiss parameters actually has those
    parameters.
    """
    beam = ParticleBeam.from_twiss(
        num_particles=torch.tensor([10_000_000]),
        beta_x=torch.tensor([5.91253676811640894]),
        alpha_x=torch.tensor([3.55631307633660354]),
        emittance_x=torch.tensor([3.494768647122823e-09]),
        beta_y=torch.tensor([5.91253676811640982]),
        alpha_y=torch.tensor([1.0]),  # TODO: set realistic value
        emittance_y=torch.tensor([3.497810737006068e-09]),
        energy=torch.tensor([6e6]),
    )
    # rather loose rtol is needed here due to the random sampling of the beam
    assert np.isclose(beam.beta_x.cpu().numpy(), 5.91253676811640894, rtol=1e-2)
    assert np.isclose(beam.alpha_x.cpu().numpy(), 3.55631307633660354, rtol=1e-2)
    assert np.isclose(beam.emittance_x.cpu().numpy(), 3.494768647122823e-09, rtol=1e-2)
    assert np.isclose(beam.beta_y.cpu().numpy(), 5.91253676811640982, rtol=1e-2)
    assert np.isclose(beam.alpha_y.cpu().numpy(), 1.0, rtol=1e-2)
    assert np.isclose(beam.emittance_y.cpu().numpy(), 3.497810737006068e-09, rtol=1e-2)
    assert np.isclose(beam.energy.cpu().numpy(), 6e6)


def test_generate_uniform_ellipsoid_batched():
    """
    Test that a `ParticleBeam` generated from a uniform 3D ellipsoid has the correct
    parameters, i.e. the all particles are within the ellipsoid, and that the other
    beam parameters are as they would be for a Gaussian beam.
    """
    radius_x = torch.tensor([1e-3, 2e-3])
    radius_y = torch.tensor([1e-4, 2e-4])
    radius_s = torch.tensor([1e-5, 2e-5])

    num_particles = torch.tensor(1_000_000)
    sigma_xp = torch.tensor([2e-7, 1e-7])
    sigma_yp = torch.tensor([3e-7, 2e-7])
    sigma_p = torch.tensor([0.000001, 0.000002])
    energy = torch.tensor([1e7, 2e7])
    total_charge = torch.tensor([1e-9, 3e-9])

    num_particles = torch.tensor(1_000_000)
    beam = ParticleBeam.uniform_3d_ellispoid(
        num_particles=num_particles,
        radius_x=radius_x,
        radius_y=radius_y,
        radius_s=radius_s,
        sigma_xp=sigma_xp,
        sigma_yp=sigma_yp,
        sigma_p=sigma_p,
        energy=energy,
        total_charge=total_charge,
    )

    assert beam.num_particles == num_particles
    assert torch.all(beam.xs.abs().transpose(0, 1) <= radius_x)
    assert torch.all(beam.ys.abs().transpose(0, 1) <= radius_y)
    assert torch.all(beam.ss.abs().transpose(0, 1) <= radius_s)
    assert torch.allclose(beam.sigma_xp, sigma_xp)
    assert torch.allclose(beam.sigma_yp, sigma_yp)
    assert torch.allclose(beam.sigma_p, sigma_p)
    assert torch.allclose(beam.energy, energy)
    assert torch.allclose(beam.total_charge, total_charge)
