"""Adversarial Research System: generates experiments designed to
disprove or weaken a strategy, not to find its best configuration
(Phase 3 brief section 5). It only GENERATES the perturbed experiments
(worse costs, parameter jitter, leave-one-period-out); judging whether a
strategy "survived" them is the future qualification system's job (out
of scope - see Phase 3 brief section 14/`Phase 3 does not need to
implement the complete qualification system yet`)."""

from app.systems.adversarial.system import AdversarialConfig, AdversarialRequest, AdversarialResearchSystem

__all__ = ["AdversarialConfig", "AdversarialRequest", "AdversarialResearchSystem"]
