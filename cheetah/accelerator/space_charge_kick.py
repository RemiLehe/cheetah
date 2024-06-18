from typing import Optional, Union

import matplotlib
import torch
from scipy import constants
from scipy.constants import physical_constants
from torch import nn

from cheetah.particles import Beam, ParticleBeam

from .element import Element

# Constants
elementary_charge = torch.tensor(constants.elementary_charge)
epsilon_0 = torch.tensor(constants.epsilon_0)
speed_of_light = torch.tensor(constants.speed_of_light)


class SpaceChargeKick(Element):
    """
    Applies the effect of space charge over a length `length`, on the **momentum**
    (i.e. divergence and energy spread) of the beam.
    The positions are unmodified ; this is meant to be combined with another lattice
    element (e.g. `Drift`) that does modify the positions, but does not take into
    account space charge.
    This uses the integrated Green function method
    (https://journals.aps.org/prab/abstract/10.1103/PhysRevSTAB.9.044204) to compute
    the effect of space charge. This is similar to the method used in Ocelot.
    The main difference is that it solves the Poisson equation in the beam frame,
    while here we solve a modified Poisson equation in the laboratory frame
    (https://pubs.aip.org/aip/pop/article-abstract/15/5/056701/1016636/Simulation-of-beams-or-plasmas-crossing-at).
    The two methods are in principle equivalent.

    Overview of the method:
    - Compute the beam charge density on a grid
    - Convolve the charge density with a Green function (the integrated green function)
    to find the potential `phi` on the grid. The convolution uses the Hockney method
    for open boundaries (allocate 2x larger arrays and perform convolution using FFTs)
    - Compute the corresponding electromagnetic fields and Lorentz force on the grid
    - Interpolate the Lorentz force to the particles and update their momentum

    :param length_effect: Length over which the effect applies in meters.
    :param length: Physical length of the element in meters (=0)
    :param num_grid_points_x, num_grid_points_y, num_grid_points_s: Number of grid
    points in each dimension.
    :param grid_extend_x, grid_extend_y, grid_extend_s: Dimensions of the grid on which
    to compute space-charge, as multiples of sigma of the beam (dimensionless)
    :param name: Unique identifier of the element.
    """

    def __init__(
        self,
        length_effect: Union[
            torch.Tensor, nn.Parameter
        ],  # TODO: Rename to effective_length
        length: Union[torch.Tensor, nn.Parameter] = 0.0,
        num_grid_points_x: Union[torch.Tensor, nn.Parameter, int] = 32,
        num_grid_points_y: Union[torch.Tensor, nn.Parameter, int] = 32,
        num_grid_points_s: Union[torch.Tensor, nn.Parameter, int] = 32,
        grid_extend_x: Union[torch.Tensor, nn.Parameter] = 3,
        grid_extend_y: Union[torch.Tensor, nn.Parameter] = 3,
        grid_extend_s: Union[torch.Tensor, nn.Parameter] = 3,
        name: Optional[str] = None,
        device=None,
        dtype=torch.float32,
    ) -> None:
        self.factory_kwargs = {"device": device, "dtype": dtype}

        super().__init__(name=name)

        self.length_effect = torch.as_tensor(length_effect, **self.factory_kwargs)
        self.length = torch.as_tensor(length, **self.factory_kwargs)
        self.grid_shape = (
            int(num_grid_points_x),
            int(num_grid_points_y),
            int(num_grid_points_s),
        )
        self.grid_extend_x = torch.as_tensor(grid_extend_x, **self.factory_kwargs)
        # In multiples of sigma
        self.grid_extend_y = torch.as_tensor(grid_extend_y, **self.factory_kwargs)
        self.grid_extend_s = torch.as_tensor(grid_extend_s, **self.factory_kwargs)

    def _compute_grid_dimensions(self, beam: ParticleBeam) -> torch.Tensor:
        """
        Computes the dimensions of the grid on which to compute the space charge effect.
        """
        # TODO: Refactor ... might not need to be a method
        return torch.stack(
            [
                self.grid_extend_x * beam.sigma_x,
                self.grid_extend_y * beam.sigma_y,
                self.grid_extend_s * beam.sigma_s,
            ],
            dim=-1,
        )

    def _deposit_charge_on_grid(
        self,
        beam: ParticleBeam,
        moments: torch.Tensor,
        cell_size: torch.Tensor,
        grid_dimensions: torch.Tensor,
    ) -> torch.Tensor:
        """
        Deposits the charge density of the beam onto a grid, using the nearest grid
        point method and weighting by the distance to the grid points. Returns a grid of
        charge density in C/m^3.
        """
        charge = torch.zeros(
            beam.particles.shape[:-2] + self.grid_shape, **self.factory_kwargs
        )

        # Get particle positions
        particle_positions = moments[..., [0, 2, 4]]
        normalized_positions = (
            particle_positions + grid_dimensions.unsqueeze(-2)
        ) / cell_size.unsqueeze(-2)

        # Find indices of the lower corners of the cells containing the particles
        cell_indices = torch.floor(normalized_positions).type(torch.long)

        # Calculate the weights for all surrounding cells
        offsets = torch.tensor(
            [
                [0, 0, 0],
                [0, 0, 1],
                [0, 1, 0],
                [0, 1, 1],
                [1, 0, 0],
                [1, 0, 1],
                [1, 1, 0],
                [1, 1, 1],
            ]
        )
        surrounding_indices = cell_indices.unsqueeze(-2) + offsets.unsqueeze(-3)
        # Shape: (..., num_particles, 8, 3)
        weights = 1 - torch.abs(
            normalized_positions.unsqueeze(-2) - surrounding_indices
        )
        # Shape: (.., num_particles, 8, 3)
        cell_weights = weights.prod(dim=-1)  # Shape: (.., num_particles, 8)

        # Add the charge contributions to the cells
        # Shape: (..., 8 * num_particles)
        idx_vector = (
            torch.arange(cell_indices.shape[0]).repeat(8 * beam.num_particles, 1).T
        )
        idx_x = surrounding_indices[..., 0].flatten(start_dim=-2)
        idx_y = surrounding_indices[..., 1].flatten(start_dim=-2)
        idx_s = surrounding_indices[..., 2].flatten(start_dim=-2)

        # Check that particles are inside the grid
        valid_mask = (
            (idx_x >= 0)
            & (idx_x < self.grid_shape[0])
            & (idx_y >= 0)
            & (idx_y < self.grid_shape[1])
            & (idx_s >= 0)
            & (idx_s < self.grid_shape[2])
        )

        # Accumulate the charge contributions
        repeated_charges = beam.particle_charges.repeat_interleave(
            repeats=8, dim=-1
        )  # Shape:(..., 8 * num_particles)
        values = (cell_weights.flatten(start_dim=-2) * repeated_charges)[valid_mask]
        charge.index_put_(
            (
                idx_vector[valid_mask],
                idx_x[valid_mask],
                idx_y[valid_mask],
                idx_s[valid_mask],
            ),
            values,
            accumulate=True,
        )

        return (
            charge
            / (cell_size[..., 0] * cell_size[..., 1] * cell_size[..., 2])[
                ..., None, None, None
            ]
        )  # Normalize by the cell volume

    def _integrated_potential(
        self, x: torch.Tensor, y: torch.Tensor, s: torch.Tensor
    ) -> torch.Tensor:
        """
        Computes the electrostatic potential using the Integrated Green Function method
        as in http://dx.doi.org/10.1103/PhysRevSTAB.9.044204.
        """

        r = torch.sqrt(x**2 + y**2 + s**2)
        integrated_potential = (
            -0.5 * s**2 * torch.atan(x * y / (s * r))
            - 0.5 * y**2 * torch.atan(x * s / (y * r))
            - 0.5 * x**2 * torch.atan(y * s / (x * r))
            + y * s * torch.asinh(x / torch.sqrt(y**2 + s**2))
            + x * s * torch.asinh(y / torch.sqrt(x**2 + s**2))
            + x * y * torch.asinh(s / torch.sqrt(x**2 + y**2))
        )
        return integrated_potential

    def _array_rho(
        self,
        beam: ParticleBeam,
        moments: torch.Tensor,
        cell_size: torch.Tensor,
        grid_dimensions: torch.Tensor,
    ) -> torch.Tensor:
        """
        Allocates a 2x larger array in all dimensions (to perform Hockney's method), and
        copies the charge density in one of the "quadrants".
        """
        charge_density = self._deposit_charge_on_grid(
            beam, moments, cell_size, grid_dimensions
        )
        new_dims = tuple(2 * dim for dim in self.grid_shape)

        # Create a new tensor with the doubled dimensions, filled with zeros
        new_charge_density = torch.zeros(
            beam.particles.shape[:-2] + new_dims, **self.factory_kwargs
        )

        # Copy the original charge_density values to the beginning of the new tensor
        new_charge_density[
            ...,
            : charge_density.shape[-3],
            : charge_density.shape[-2],
            : charge_density.shape[-1],
        ] = charge_density

        return new_charge_density

    def _integrated_green_function(
        self, beam: ParticleBeam, cell_size: torch.Tensor
    ) -> torch.Tensor:
        """
        Computes the Integrated Green Function (IGF) with periodic boundary conditions
        (to perform Hockney's method).
        """
        dx, dy, ds = (
            cell_size[..., 0],
            cell_size[..., 1],
            cell_size[..., 2] * beam.relativistic_gamma,
        )  # Scaled by gamma
        num_grid_points_x, num_grid_points_y, num_grid_points_s = self.grid_shape

        # Create coordinate grids
        x = torch.arange(num_grid_points_x, **self.factory_kwargs)
        y = torch.arange(num_grid_points_y, **self.factory_kwargs)
        s = torch.arange(num_grid_points_s, **self.factory_kwargs)
        ix_grid, iy_grid, is_grid = torch.meshgrid(x, y, s, indexing="ij")
        x_grid = (
            ix_grid[None, :, :, :] * dx[..., None, None, None]
        )  # Shape: [..., nx, ny, nz]
        y_grid = (
            iy_grid[None, :, :, :] * dy[..., None, None, None]
        )  # Shape: [..., nx, ny, nz]
        s_grid = (
            is_grid[None, :, :, :] * ds[..., None, None, None]
        )  # Shape: [..., nx, ny, nz]

        # Compute the Green's function values
        G_values = (
            self._integrated_potential(
                x_grid + 0.5 * dx[..., None, None, None],
                y_grid + 0.5 * dy[..., None, None, None],
                s_grid + 0.5 * ds[..., None, None, None],
            )
            - self._integrated_potential(
                x_grid - 0.5 * dx[..., None, None, None],
                y_grid + 0.5 * dy[..., None, None, None],
                s_grid + 0.5 * ds[..., None, None, None],
            )
            - self._integrated_potential(
                x_grid + 0.5 * dx[..., None, None, None],
                y_grid - 0.5 * dy[..., None, None, None],
                s_grid + 0.5 * ds[..., None, None, None],
            )
            - self._integrated_potential(
                x_grid + 0.5 * dx[..., None, None, None],
                y_grid + 0.5 * dy[..., None, None, None],
                s_grid - 0.5 * ds[..., None, None, None],
            )
            + self._integrated_potential(
                x_grid + 0.5 * dx[..., None, None, None],
                y_grid - 0.5 * dy[..., None, None, None],
                s_grid - 0.5 * ds[..., None, None, None],
            )
            + self._integrated_potential(
                x_grid - 0.5 * dx[..., None, None, None],
                y_grid + 0.5 * dy[..., None, None, None],
                s_grid - 0.5 * ds[..., None, None, None],
            )
            + self._integrated_potential(
                x_grid - 0.5 * dx[..., None, None, None],
                y_grid - 0.5 * dy[..., None, None, None],
                s_grid + 0.5 * ds[..., None, None, None],
            )
            - self._integrated_potential(
                x_grid - 0.5 * dx[..., None, None, None],
                y_grid - 0.5 * dy[..., None, None, None],
                s_grid - 0.5 * ds[..., None, None, None],
            )
        )

        # Initialize the grid with double dimensions
        green_func_values = torch.zeros(
            (
                *beam.particles.shape[:-2],
                2 * num_grid_points_x,
                2 * num_grid_points_y,
                2 * num_grid_points_s,
            ),
            **self.factory_kwargs,
        )

        # Fill the grid with G_values and its periodic copies
        green_func_values[
            ..., :num_grid_points_x, :num_grid_points_y, :num_grid_points_s
        ] = G_values
        green_func_values[
            ..., num_grid_points_x + 1 :, :num_grid_points_y, :num_grid_points_s
        ] = G_values[..., 1:, :, :].flip(
            dims=[-3]
        )  # Reverse x, excluding the first element
        green_func_values[
            ..., :num_grid_points_x, num_grid_points_y + 1 :, :num_grid_points_s
        ] = G_values[..., :, 1:, :].flip(
            dims=[-2]
        )  # Reverse y, excluding the first element
        green_func_values[
            ..., :num_grid_points_x, :num_grid_points_y, num_grid_points_s + 1 :
        ] = G_values[..., :, :, 1:].flip(
            dims=[-1]
        )  # Reverse s, excluding the first element
        green_func_values[
            ..., num_grid_points_x + 1 :, num_grid_points_y + 1 :, :num_grid_points_s
        ] = G_values[..., 1:, 1:, :].flip(
            dims=[-3, -2]
        )  # Reverse the x and y dimensions
        green_func_values[
            ..., :num_grid_points_x, num_grid_points_y + 1 :, num_grid_points_s + 1 :
        ] = G_values[..., :, 1:, 1:].flip(
            dims=[-2, -1]
        )  # Reverse the y and s dimensions
        green_func_values[
            ..., num_grid_points_x + 1 :, :num_grid_points_y, num_grid_points_s + 1 :
        ] = G_values[..., 1:, :, 1:].flip(
            dims=[-3, -1]
        )  # Reverse the x and s dimensions
        green_func_values[
            ...,
            num_grid_points_x + 1 :,
            num_grid_points_y + 1 :,
            num_grid_points_s + 1 :,
        ] = G_values[..., 1:, 1:, 1:].flip(
            dims=[-3, -2, -1]
        )  # Reverse all dimensions

        return green_func_values

    def _solve_poisson_equation(
        self, beam: ParticleBeam, moments: torch.Tensor, cell_size, grid_dimensions
    ) -> torch.Tensor:  # Works only for ParticleBeam at this stage
        """
        Solves the Poisson equation for the given charge density, using FFT convolution.
        """
        charge_density = self._array_rho(beam, moments, cell_size, grid_dimensions)
        charge_density_ft = torch.fft.fftn(charge_density, dim=[1, 2, 3])
        integrated_green_function = self._integrated_green_function(beam, cell_size)
        integrated_green_function_ft = torch.fft.fftn(
            integrated_green_function, dim=[1, 2, 3]
        )
        potential_ft = charge_density_ft * integrated_green_function_ft
        potential = (1 / (4 * torch.pi * epsilon_0)) * torch.fft.ifftn(
            potential_ft, dim=[1, 2, 3]
        ).real

        # Return the physical potential
        return potential[
            ...,
            : charge_density.shape[-3] // 2,
            : charge_density.shape[-2] // 2,
            : charge_density.shape[-1] // 2,
        ]

    def _E_plus_vB_field(
        self,
        beam: ParticleBeam,
        moments: torch.Tensor,
        cell_size: torch.Tensor,
        grid_dimensions: torch.Tensor,
    ) -> torch.Tensor:
        """
        Computes the force field from the potential and the particle positions and
        speeds, as in https://doi.org/10.1063/1.2837054.
        """
        inv_cell_size = 1 / cell_size
        igamma2 = torch.zeros_like(beam.relativistic_gamma)
        igamma2[beam.relativistic_gamma != 0] = (
            1 / beam.relativistic_gamma[beam.relativistic_gamma != 0] ** 2
        )
        potential = self._solve_poisson_equation(
            beam, moments, cell_size, grid_dimensions
        )

        grad_x = torch.zeros_like(potential)
        grad_y = torch.zeros_like(potential)
        grad_s = torch.zeros_like(potential)

        # Compute the gradients of the potential, using central differences, with 0
        # boundary conditions
        grad_x[..., 1:-1, :, :] = (
            potential[..., 2:, :, :] - potential[..., :-2, :, :]
        ) * (0.5 * inv_cell_size[..., 0, None, None, None])
        grad_y[..., :, 1:-1, :] = (
            potential[..., :, 2:, :] - potential[..., :, :-2, :]
        ) * (0.5 * inv_cell_size[..., 1, None, None, None])
        grad_s[..., :, :, 1:-1] = (
            potential[..., :, :, 2:] - potential[..., :, :, :-2]
        ) * (0.5 * inv_cell_size[..., 2, None, None, None])

        # Scale the gradients with lorentz factor
        grad_x = -igamma2[..., None, None, None] * grad_x
        grad_y = -igamma2[..., None, None, None] * grad_y
        grad_s = -igamma2[..., None, None, None] * grad_s

        return grad_x, grad_y, grad_s

    def _compute_forces(
        self,
        beam: ParticleBeam,
        moments: torch.Tensor,
        cell_size: torch.Tensor,
        grid_dimensions: torch.Tensor,
    ) -> torch.Tensor:
        """
        Interpolates the space charge force from the grid onto the macroparticles.
        Reciprocal function of _deposit_charge_on_grid.
        """
        grad_x, grad_y, grad_z = self._E_plus_vB_field(
            beam, moments, cell_size, grid_dimensions
        )
        grid_shape = self.grid_shape
        interpolated_forces = torch.zeros(
            (*beam.particles.shape[:-1], 3), **self.factory_kwargs
        )

        # Get particle positions
        particle_positions = moments[..., [0, 2, 4]]
        normalized_positions = (
            particle_positions + grid_dimensions.unsqueeze(-2)
        ) / cell_size.unsqueeze(-2)

        # Find indices of the lower corners of the cells containing the particles
        cell_indices = torch.floor(normalized_positions).type(torch.long)

        # Calculate the weights for all surrounding cells
        offsets = torch.tensor(
            [
                [0, 0, 0],
                [0, 0, 1],
                [0, 1, 0],
                [0, 1, 1],
                [1, 0, 0],
                [1, 0, 1],
                [1, 1, 0],
                [1, 1, 1],
            ]
        )
        surrounding_indices = cell_indices.unsqueeze(-2) + offsets.unsqueeze(
            -3
        )  # Shape:(.., num_particles, 8, 3)
        weights = 1 - torch.abs(
            normalized_positions.unsqueeze(-2) - surrounding_indices
        )  # Shape: (..., num_particles, 8, 3)
        cell_weights = weights.prod(dim=-1)  # Shape: (..., num_particles, 8)

        # Extract forces from the grids
        surrounding_indices_flattened = surrounding_indices.flatten(
            start_dim=-3, end_dim=-2
        )  # Shape: (..., num_particles * 8, 3)
        idx_vector = (
            torch.arange(cell_indices.shape[0]).repeat(8 * beam.num_particles, 1).T
        )
        idx_x = surrounding_indices_flattened[..., 0]
        idx_y = surrounding_indices_flattened[..., 1]
        idx_s = surrounding_indices_flattened[..., 2]
        valid_mask = (
            (idx_x >= 0)
            & (idx_x < grid_shape[0])
            & (idx_y >= 0)
            & (idx_y < grid_shape[1])
            & (idx_s >= 0)
            & (idx_s < grid_shape[2])
        )

        valid_indices = (
            idx_vector[valid_mask],
            idx_x[valid_mask],
            idx_y[valid_mask],
            idx_s[valid_mask],
        )

        Fx_values = grad_x[valid_indices]
        Fy_values = grad_y[valid_indices]
        Fz_values = grad_z[valid_indices]

        # Compute interpolated forces
        valid_cell_weights = (
            cell_weights.flatten(start_dim=-2)[valid_mask] * elementary_charge
        )
        values_x = valid_cell_weights * Fx_values
        values_y = valid_cell_weights * Fy_values
        values_z = valid_cell_weights * Fz_values

        indices = (
            torch.arange(beam.num_particles)
            .repeat_interleave(8)
            .repeat(cell_weights.shape[0], 1)[valid_mask]
        )  # TODO: Indicies of what?

        interpolated_forces[:, indices, 0] += values_x
        interpolated_forces[:, indices, 1] += values_y
        interpolated_forces[:, indices, 2] += values_z

        return interpolated_forces

    def track(self, incoming: ParticleBeam) -> ParticleBeam:
        """
        Tracks particles through the element. The input must be a `ParticleBeam`.

        :param incoming: Beam of particles entering the element.
        :returns: Beam of particles exiting the element.
        """
        if incoming is Beam.empty or incoming.particles.shape[0] == 0:
            return incoming
        elif isinstance(incoming, ParticleBeam):
            # This flattening is a hack to only think about one vector dimension in the
            # following code. It is reversed at the end of the function.
            flattened_incoming = ParticleBeam(
                particles=incoming.particles.flatten(end_dim=-3),
                energy=incoming.energy.flatten(end_dim=-1),
                particle_charges=incoming.particle_charges.flatten(end_dim=-2),
                device=incoming.particles.device,
                dtype=incoming.particles.dtype,
            )
            flattened_length_effect = self.length_effect.flatten(end_dim=-1)

            # Compute useful quantities
            grid_dimensions = self._compute_grid_dimensions(flattened_incoming)
            cell_size = 2 * grid_dimensions / torch.tensor(self.grid_shape)
            dt = flattened_length_effect / (
                speed_of_light * flattened_incoming.relativistic_beta
            )

            # Change coordinates to apply the space charge effect
            moments = flattened_incoming.to_moments()
            forces = self._compute_forces(
                flattened_incoming, moments, cell_size, grid_dimensions
            )
            moments[..., 1] = moments[..., 1] + forces[..., 0] * dt.unsqueeze(-1)
            moments[..., 3] = moments[..., 3] + forces[..., 1] * dt.unsqueeze(-1)
            moments[..., 5] = moments[..., 5] + forces[..., 2] * dt.unsqueeze(-1)

            outgoing = ParticleBeam.from_moments(
                moments.unflatten(dim=0, sizes=incoming.particles.shape[:-2]),
                incoming.energy,
                incoming.particle_charges,
                incoming.particles.device,
                incoming.particles.dtype,
            )

            return outgoing
        else:
            raise TypeError(f"Parameter incoming is of invalid type {type(incoming)}")

    def broadcast(self, shape: torch.Size) -> "SpaceChargeKick":
        """
        Broadcast the element to higher batch dimensions.

        :param shape: Shape to broadcast the element to.
        :returns: Broadcasted element.
        """
        return self.__class__(
            length_effect=self.length_effect,
            length=self.length,
            num_grid_points_x=self.grid_shape[0],
            num_grid_points_y=self.grid_shape[1],
            num_grid_points_s=self.grid_shape[2],
            grid_extend_x=self.grid_extend_x,
            grid_extend_y=self.grid_extend_y,
            grid_extend_s=self.grid_extend_s,
            name=self.name,
        )

    def split(self, resolution: torch.Tensor) -> list[Element]:
        # TODO: Implement splitting for SpaceCharge properly, for now just returns the
        # element itself
        return [self]

    @property
    def is_skippable(self) -> bool:
        return False

    def plot(self, ax: matplotlib.axes.Axes, s: float) -> None:
        pass

    @property
    def defining_features(self) -> list[str]:
        return super().defining_features + ["length"]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(length={repr(self.length)})"
