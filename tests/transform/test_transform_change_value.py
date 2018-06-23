""" Tests of change value transform.

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2018-06-19
:Copyright: 2018, Karr Lab
:License: MIT
"""

from wc_lang import (Model, Compartment, Concentration, Function, Parameter, RateLawDirection, RateLawEquation, Reaction, Species)
from wc_lang.transform import ChangeValueTransform
import unittest


class ChangeValueTransformTestCase(unittest.TestCase):

    def test_compartment_initial_volume(self):
        model = Model()
        c = model.compartments.create(id='c', initial_volume=1.)
        e = model.compartments.create(id='e', initial_volume=1.)
        ChangeValueTransform(Compartment, 'c', ['initial_volume'], 2.).run(model)

        self.assertEqual(c.initial_volume, 2.)
        self.assertEqual(e.initial_volume, 1.)

    def test_function_expression(self):
        model = Model()
        f = model.functions.create(id='f', expression='x')
        g = model.functions.create(id='g', expression='y')
        ChangeValueTransform(Function, 'g', ['expression'], 'z').run(model)

        self.assertEqual(f.expression, 'x')
        self.assertEqual(g.expression, 'z')

    def test_parameter_units(self):
        model = Model()
        p_1 = model.parameters.create(id='p_1', units='M')
        p_2 = model.parameters.create(id='p_2', units='L')
        ChangeValueTransform(Parameter, 'p_1', ['units'], 'm^2').run(model)

        self.assertEqual(p_1.units, 'm^2')
        self.assertEqual(p_2.units, 'L')

    def test_parameter_value(self):
        model = Model()
        p_1 = model.parameters.create(id='p_1', value=1)
        p_2 = model.parameters.create(id='p_2', value=3)
        ChangeValueTransform(Parameter, 'p_1', ['value'], 2).run(model)

        self.assertEqual(p_1.value, 2)
        self.assertEqual(p_2.value, 3)

    def test_reaction_reversible(self):
        model = Model()
        s_1 = model.submodels.create(id='s_1')
        s_2 = model.submodels.create(id='s_2')
        r_1_1 = s_1.reactions.create(id='r_1_1', reversible=False)
        r_1_2 = s_1.reactions.create(id='r_1_2', reversible=False)
        r_2_1 = s_2.reactions.create(id='r_2_1', reversible=True)
        r_2_2 = s_2.reactions.create(id='r_2_2', reversible=True)
        ChangeValueTransform(Reaction, 'r_2_1', ['reversible'], False).run(model)

        self.assertEqual(r_1_1.reversible, False)
        self.assertEqual(r_1_2.reversible, False)
        self.assertEqual(r_2_1.reversible, False)
        self.assertEqual(r_2_2.reversible, True)

    def test_reaction_min_flux(self):
        model = Model()
        s_1 = model.submodels.create(id='s_1')
        s_2 = model.submodels.create(id='s_2')
        r_1_1 = s_1.reactions.create(id='r_1_1', min_flux=1)
        r_1_2 = s_1.reactions.create(id='r_1_2', min_flux=2)
        r_2_1 = s_2.reactions.create(id='r_2_1', min_flux=3)
        r_2_2 = s_2.reactions.create(id='r_2_2', min_flux=4)
        ChangeValueTransform(Reaction, 'r_1_2', ['min_flux'], 0).run(model)

        self.assertEqual(r_1_1.min_flux, 1)
        self.assertEqual(r_1_2.min_flux, 0)
        self.assertEqual(r_2_1.min_flux, 3)
        self.assertEqual(r_2_2.min_flux, 4)

    def test_reaction_max_flux(self):
        model = Model()
        s_1 = model.submodels.create(id='s_1')
        s_2 = model.submodels.create(id='s_2')
        r_1_1 = s_1.reactions.create(id='r_1_1', max_flux=1)
        r_1_2 = s_1.reactions.create(id='r_1_2', max_flux=2)
        r_2_1 = s_2.reactions.create(id='r_2_1', max_flux=3)
        r_2_2 = s_2.reactions.create(id='r_2_2', max_flux=4)
        ChangeValueTransform(Reaction, 'r_2_2', ['max_flux'], 0).run(model)

        self.assertEqual(r_1_1.max_flux, 1)
        self.assertEqual(r_1_2.max_flux, 2)
        self.assertEqual(r_2_1.max_flux, 3)
        self.assertEqual(r_2_2.max_flux, 0)

    def test_reaction_equation(self):
        model = Model()
        s_1 = model.submodels.create(id='s_1')
        r_1_1 = s_1.reactions.create(id='r_1_1')
        rl_f = r_1_1.rate_laws.create(direction=RateLawDirection.forward, equation=RateLawEquation(expression='x'))
        rl_b = r_1_1.rate_laws.create(direction=RateLawDirection.backward, equation=RateLawEquation(expression='y'))
        ChangeValueTransform(Reaction, 'r_1_1', ['rate_laws', 'forward', 'equation', 'expression'], 'z').run(model)

        self.assertEqual(rl_f.equation.expression, 'z')
        self.assertEqual(rl_b.equation.expression, 'y')

    def test_reaction_k_cat(self):
        model = Model()
        s_1 = model.submodels.create(id='s_1')
        r_1_1 = s_1.reactions.create(id='r_1_1')
        rl_f = r_1_1.rate_laws.create(direction=RateLawDirection.forward, k_cat=1)
        rl_b = r_1_1.rate_laws.create(direction=RateLawDirection.backward, k_cat=2)
        ChangeValueTransform(Reaction, 'r_1_1', ['rate_laws', 'backward', 'k_cat'], 0).run(model)

        self.assertEqual(rl_f.k_cat, 1)
        self.assertEqual(rl_b.k_cat, 0)

    def test_reaction_k_m(self):
        model = Model()
        s_1 = model.submodels.create(id='s_1')
        r_1_1 = s_1.reactions.create(id='r_1_1')
        rl_f = r_1_1.rate_laws.create(direction=RateLawDirection.forward, k_m=1)
        rl_b = r_1_1.rate_laws.create(direction=RateLawDirection.backward, k_m=2)
        ChangeValueTransform(Reaction, 'r_1_1', ['rate_laws', 'backward', 'k_m'], 0).run(model)

        self.assertEqual(rl_f.k_m, 1)
        self.assertEqual(rl_b.k_m, 0)

    def test_species_concentration_units(self):
        model = Model()
        st_1 = model.species_types.create(id='st_1')
        st_2 = model.species_types.create(id='st_2')
        c_1 = model.compartments.create(id='c_1')
        c_2 = model.compartments.create(id='c_2')
        st_1_c_1 = st_1.species.create(compartment=c_1)
        st_1_c_2 = st_1.species.create(compartment=c_2)
        st_2_c_1 = st_2.species.create(compartment=c_1)
        st_2_c_2 = st_2.species.create(compartment=c_2)

        st_1_c_1.concentration = Concentration(units='u')
        st_1_c_2.concentration = Concentration(units='v')
        st_2_c_1.concentration = Concentration(units='w')
        st_2_c_2.concentration = Concentration(units='x')

        ChangeValueTransform(Species, 'st_1[c_1]', ['concentration', 'units'], 'a').run(model)
        self.assertEqual(st_1_c_1.concentration.units, 'a')
        self.assertEqual(st_1_c_2.concentration.units, 'v')
        self.assertEqual(st_2_c_1.concentration.units, 'w')
        self.assertEqual(st_2_c_2.concentration.units, 'x')

    def test_species_concentration_value(self):
        model = Model()
        st_1 = model.species_types.create(id='st_1')
        st_2 = model.species_types.create(id='st_2')
        c_1 = model.compartments.create(id='c_1')
        c_2 = model.compartments.create(id='c_2')
        st_1_c_1 = st_1.species.create(compartment=c_1)
        st_1_c_2 = st_1.species.create(compartment=c_2)
        st_2_c_1 = st_2.species.create(compartment=c_1)
        st_2_c_2 = st_2.species.create(compartment=c_2)

        st_1_c_1.concentration = Concentration(value=1)
        st_1_c_2.concentration = Concentration(value=2)
        st_2_c_1.concentration = Concentration(value=3)
        st_2_c_2.concentration = Concentration(value=4)

        ChangeValueTransform(Species, 'st_2[c_1]', ['concentration', 'value'], 0).run(model)
        self.assertEqual(st_1_c_1.concentration.value, 1)
        self.assertEqual(st_1_c_2.concentration.value, 2)
        self.assertEqual(st_2_c_1.concentration.value, 0)
        self.assertEqual(st_2_c_2.concentration.value, 4)