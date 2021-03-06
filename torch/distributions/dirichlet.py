from numbers import Number

import torch
from torch.autograd import Function, Variable
from torch.autograd.function import once_differentiable
from torch.distributions import constraints
from torch.distributions.distribution import Distribution
from torch.distributions.utils import _finfo, broadcast_all


def _dirichlet_sample_nograd(concentration):
    probs = torch._C._standard_gamma(concentration)
    probs /= probs.sum(-1, True)
    eps = _finfo(probs).eps
    return probs.clamp_(min=eps, max=1 - eps)


# This helper is exposed for testing.
def _Dirichlet_backward(x, concentration, grad_output):
    total = concentration.sum(-1, True).expand_as(concentration)
    grad = torch._C._dirichlet_grad(x, concentration, total)
    return grad * (grad_output - (x * grad_output).sum(-1, True))


class _Dirichlet(Function):
    @staticmethod
    def forward(ctx, concentration):
        x = _dirichlet_sample_nograd(concentration)
        ctx.save_for_backward(x, concentration)
        return x

    @staticmethod
    @once_differentiable
    def backward(ctx, grad_output):
        x, concentration = ctx.saved_tensors
        return _Dirichlet_backward(x, concentration, grad_output)


class Dirichlet(Distribution):
    r"""
    Creates a Dirichlet distribution parameterized by concentration `concentration`.

    Example::

        >>> m = Dirichlet(torch.Tensor([0.5, 0.5]))
        >>> m.sample()  # Dirichlet distributed with concentrarion concentration
         0.1046
         0.8954
        [torch.FloatTensor of size 2]

    Args:
        concentration (Tensor or Variable): concentration parameter of the distribution
            (often referred to as alpha)
    """
    params = {'concentration': constraints.positive}
    support = constraints.simplex
    has_rsample = True

    def __init__(self, concentration):
        self.concentration, = broadcast_all(concentration)
        batch_shape, event_shape = concentration.shape[:-1], concentration.shape[-1:]
        super(Dirichlet, self).__init__(batch_shape, event_shape)

    def rsample(self, sample_shape=()):
        shape = self._extended_shape(sample_shape)
        concentration = self.concentration.expand(shape)
        if isinstance(concentration, Variable):
            return _Dirichlet.apply(concentration)
        return _dirichlet_sample_nograd(concentration)

    def log_prob(self, value):
        self._validate_log_prob_arg(value)
        return ((torch.log(value) * (self.concentration - 1.0)).sum(-1) +
                torch.lgamma(self.concentration.sum(-1)) -
                torch.lgamma(self.concentration).sum(-1))

    def entropy(self):
        k = self.concentration.size(-1)
        a0 = self.concentration.sum(-1)
        return (torch.lgamma(self.concentration).sum(-1) - torch.lgamma(a0) -
                (k - a0) * torch.digamma(a0) -
                ((self.concentration - 1.0) * torch.digamma(self.concentration)).sum(-1))
