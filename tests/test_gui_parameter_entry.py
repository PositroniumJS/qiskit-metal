# This code is part of Qiskit.
#
# (C) Copyright IBM 2017, 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Parameter-entry window regressions: the QLibrary "new component" dialog.

Guards two coupled defects in ``generate_model_data``'s type handling that
together made *every* QComponent without its own ``__init__`` fail to
instantiate from the GUI's QLibrary tab:

1. ``create_default_from_type`` predates PEP 604, so it matched ``Dict``
   but not ``Dict | None`` (a ``types.UnionType``). Union-annotated params
   fell through to the ``np.ndarray(1)`` catch-all.

2. That bogus array was handed to ``QComponent.__init__`` as
   ``component_template``, which ``get_template_options`` unpacks with
   ``{**renderer_key_values, **component_template}`` -> ``TypeError:
   'numpy.ndarray' object is not a mapping``.

Fixing (1) alone is not enough, and is why ``component_template`` is now
ignored outright: it is a *registration-time* knob merged into
``design.template_options[<class>]`` on first registration, so a
synthesized placeholder does not just clutter the dialog -- it persists
into every later instance of that class in the design. The
``options`` param is the contrasting case: it is union-annotated too, but
``generate_model_data`` overwrites it with real template options, so it
never reaches the component.

Skips when PySide6 is absent (lite install); the module imports Qt at
top level even though the functions under test are pure.
"""

import copy
from inspect import signature

import numpy as np
import pytest

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from qiskit_metal._gui.widgets.create_component_window.parameter_entry_window import (  # noqa: E402
    ParameterEntryWindow,
    create_default_from_type,
)
from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal.qlibrary.core.base import QComponent  # noqa: E402
from qiskit_metal.qlibrary.lumped.cap_3_interdigital import (  # noqa: E402
    Cap3Interdigital,
)
from qiskit_metal.qlibrary.lumped.cap_n_interdigital import (  # noqa: E402
    CapNInterdigital,
)
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket  # noqa: E402
from qiskit_metal.qlibrary.sample_shapes.n_gon import NGon  # noqa: E402

# Components that inherit QComponent.__init__ verbatim -- the population that
# hit the original TypeError. Cap3Interdigital is the reported reproducer.
INHERITED_INIT_COMPONENTS = [
    Cap3Interdigital,
    CapNInterdigital,
    TransmonPocket,
    NGon,
]


def build_param_dict(cls, design):
    """Mirror of ``ParameterEntryWindow.generate_model_data``.

    Reproduces the dialog's parameter synthesis without constructing a
    QMainWindow, so the regression is checked without a display.
    """
    param_dict = {}
    for _, param in signature(cls.__init__).parameters.items():
        if not ParameterEntryWindow.is_param_usable(param):
            continue
        if param.default:
            param_dict[param.name] = param.default
        else:
            class_name = cls.__name__ if param.name == "name" else None
            param_dict[param.name] = create_default_from_type(
                param.annotation, param_name=class_name
            )

    options = cls.get_template_options(design)
    if options is not None:
        param_dict["options"] = copy.deepcopy(options)
    return param_dict


class TestCreateDefaultFromType:
    """``create_default_from_type`` against PEP 604 annotations."""

    def test_optional_dict_is_not_ndarray(self):
        """``Dict | None`` must resolve via the Dict branch, not the catch-all."""
        annotation = signature(QComponent.__init__).parameters["options"].annotation
        result = create_default_from_type(annotation)
        assert not isinstance(result, np.ndarray)
        assert isinstance(result, dict)

    def test_optional_str_is_not_ndarray(self):
        """``str | None`` must resolve via the str branch."""
        assert isinstance(create_default_from_type(str | None), str)

    def test_optional_int_is_not_ndarray(self):
        """``int | None`` must resolve via the int branch."""
        assert isinstance(create_default_from_type(int | None), int)

    def test_bare_types_still_resolve(self):
        """Non-union annotations keep their existing behaviour."""
        assert isinstance(create_default_from_type(str), str)
        assert isinstance(create_default_from_type(int), int)
        assert create_default_from_type(bool) is True


class TestComponentTemplateIsNotExposed:
    """``component_template`` must never reach the dialog or the design."""

    def test_is_param_usable_rejects_component_template(self):
        """The dialog filters it out before any value is synthesized."""
        param = signature(QComponent.__init__).parameters["component_template"]
        assert ParameterEntryWindow.is_param_usable(param) is False

    def test_still_accepts_real_user_params(self):
        """The filter must not over-reach onto genuinely editable params."""
        params = signature(QComponent.__init__).parameters
        assert ParameterEntryWindow.is_param_usable(params["name"]) is True
        assert ParameterEntryWindow.is_param_usable(params["options"]) is True

    @pytest.mark.parametrize("cls", INHERITED_INIT_COMPONENTS, ids=lambda c: c.__name__)
    def test_component_template_absent_from_param_dict(self, cls):
        """No ``component_template`` row is offered for editing."""
        design = DesignPlanar()
        assert "component_template" not in build_param_dict(cls, design)

    @pytest.mark.parametrize("cls", INHERITED_INIT_COMPONENTS, ids=lambda c: c.__name__)
    def test_instantiates_from_gui_param_dict(self, cls):
        """The reported failure: instantiation raised TypeError (not a mapping)."""
        design = DesignPlanar()
        param_dict = build_param_dict(cls, design)
        component = cls(design, **param_dict)
        assert component.name in design.components

    @pytest.mark.parametrize("cls", INHERITED_INIT_COMPONENTS, ids=lambda c: c.__name__)
    def test_no_placeholder_leaks_into_template_options(self, cls):
        """A synthesized template would persist for every later instance."""
        design = DesignPlanar()
        cls(design, **build_param_dict(cls, design))

        registered = dict(design.template_options[cls._get_unique_class_name()])
        leaked = [
            key
            for key in registered
            if "falseparam" in key.lower() or "fake-param" in key.lower()
        ]
        assert not leaked, f"placeholder keys leaked into template_options: {leaked}"
