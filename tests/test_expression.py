'''
:Author: Arthur Goldberg, Arthur.Goldberg@mssm.edu
:Date: 2017-10-23
:Copyright: 2016-2017, Karr Lab
:License: MIT
'''

import unittest
import os
import re
import tokenize
import token
from io import BytesIO

import obj_model
from wc_lang.io import Reader
from wc_lang import (RateLawExpression, RateLaw, Reaction, Submodel, SpeciesType, Species,
                     FunctionExpression, Function,
                     StopCondition, Observable, Parameter,
                     DfbaNetReaction, Compartment)
from wc_lang.expression import (WcTokenCodes, WcToken, LexMatch,
                                ParsedExpression, ParsedExpressionError,
                                ParsedExpressionVerifier, LinearParsedExpressionVerifier)


class TestWcLangExpression(unittest.TestCase):

    def setUp(self):
        self.objects = {
            SpeciesType: {
                'test': SpeciesType(id='test'),
                'x': SpeciesType(id='x'),
            },
            Compartment: {
                'c': Compartment(id='c'),
            },
            Species: {
                'test_id[c]': Species(id='test_id[c]'),
                'x_id[c]': Species(id='x_id[c]'),
            },
            Parameter: {
                'test_id': Parameter(id='test_id'),
                'param_id': Parameter(id='param_id'),
            },
            Observable: {
                'test_id': Observable(id='test_id'),
                'obs_id': Observable(id='obs_id'),
            },
            Function: {
                'fun_1': Function(id='fun_1'),
                'fun_2': Function(id='fun_2'),
            }
        }

        # more complex objects
        self.objects_hard = {
            Species: {
                'test_id[c]': Species(),
                'x_id[c]': Species(),
            },
            Parameter: {
                'Observable': Parameter(),
                'duped_id': Parameter(),
            },
            Observable: {
                'test_id': Observable(),
                'duped_id': Observable(),
            },
            Function: {
                'Observable': Function(),
                'fun_2': Function(),
            }
        }

    @staticmethod
    def esc_re_center(re_list):
        return '.*' + '.*'.join([re.escape(an_re) for an_re in re_list]) + '.*'

    def make_wc_lang_expr(self, expr, obj_type=RateLawExpression):
        objects = self.objects.copy()
        return ParsedExpression(obj_type, 'expr_attr', expr, objects)

    def test_wc_lang_expression(self):
        expr = '3 + 5 * 6'
        wc_lang_expr = ParsedExpression(RateLawExpression, 'attr', ' ' + expr + ' ', self.objects)
        self.assertEqual(expr, wc_lang_expr.expression)
        n = 5
        wc_lang_expr = ParsedExpression(RateLawExpression, 'attr', ' + ' * n, self.objects)
        self.assertEqual([token.PLUS] * n, [tok.exact_type for tok in wc_lang_expr.py_tokens])
        wc_lang_expr = ParsedExpression(RateLawExpression, 'attr', '', {})
        self.assertEqual(wc_lang_expr.valid_functions, set(RateLawExpression.Meta.valid_functions))
        wc_lang_expr = ParsedExpression(RateLawExpression, 'attr', '', {Function: {}, Parameter: {}})
        self.assertEqual(wc_lang_expr.valid_functions, set(RateLawExpression.Meta.valid_functions))
        expr = 'id1[id2'
        with self.assertRaisesRegex(
                ParsedExpressionError,
                "parsing '{}'.*creates a Python syntax error.*".format(re.escape(expr))):
            self.make_wc_lang_expr(expr)
        with self.assertRaisesRegex(
                ParsedExpressionError,
                "model_cls 'Species' doesn't have a 'Meta.valid_models' attribute"):
            ParsedExpression(Species, 'attr', '', {})

    def test_get_model_type(self):
        wc_lang_expr = ParsedExpression(RateLawExpression, None, 'expr', self.objects)
        self.assertEqual(None, wc_lang_expr.get_model_type('NoSuchType'))
        self.assertEqual(Parameter, wc_lang_expr.get_model_type('Parameter'))
        self.assertEqual(Observable, wc_lang_expr.get_model_type('Observable'))

    def do_match_tokens_test(self, expr, pattern, expected, idx=0):
        wc_lang_expr = self.make_wc_lang_expr(expr)
        self.assertEqual(wc_lang_expr.match_tokens(pattern, idx), expected)

    def test_match_tokens(self):
        self.do_match_tokens_test('', [], False)
        single_name_pattern = (token.NAME, )
        self.do_match_tokens_test('', single_name_pattern, False)
        self.do_match_tokens_test('ID2', single_name_pattern, 'ID2')
        self.do_match_tokens_test('ID3 5', single_name_pattern, 'ID3')
        # fail to match tokens
        self.do_match_tokens_test('+ 5', single_name_pattern, False)
        # call match_tokens with 0<idx
        self.do_match_tokens_test('7 ID3', single_name_pattern, 'ID3', idx=1)
        self.do_match_tokens_test('2+ 5', single_name_pattern, False, idx=1)

        species_pattern = Species.Meta.token_pattern
        self.do_match_tokens_test('sp1[c1]+', species_pattern, 'sp1[c1]')
        self.do_match_tokens_test('sp1 +', species_pattern, False)
        # whitespace is not allowed between tokens in an ID
        self.do_match_tokens_test('sp1 [ c1 ] ', species_pattern, False)

    def do_disambiguated_id_error_test(self, expr, expected):
        wc_lang_expr = self.make_wc_lang_expr(expr)
        result = wc_lang_expr.get_disambiguated_id(0)
        self.assertTrue(isinstance(result, str))
        self.assertIn(expected.format(expr), result)

    def do_disambiguated_id_test(self, expr, disambig_type, id, pattern, case_fold_match=False):
        wc_lang_expr = self.make_wc_lang_expr(expr)
        lex_match = wc_lang_expr.get_disambiguated_id(0, case_fold_match=case_fold_match)
        self.assertTrue(isinstance(lex_match, LexMatch))
        self.assertEqual(lex_match.num_py_tokens, len(pattern))
        self.assertEqual(len(lex_match.wc_tokens), 1)
        wc_token = lex_match.wc_tokens[0]
        self.assertEqual(wc_token,
                         # note: wc_token.model is cheating
                         WcToken(WcTokenCodes.wc_obj_id, expr, disambig_type,
                                 id, wc_token.model))

    def test_disambiguated_id(self):
        self.do_disambiguated_id_error_test(
            'NotFunction.foo()',
            "contains '{}', which doesn't use 'Function' as a disambiguation model type")
        self.do_disambiguated_id_error_test(
            'Function.foo2()',
            "contains '{}', which doesn't refer to a Function")

        self.do_disambiguated_id_test('Function.fun_1()', Function, 'fun_1',
                                      ParsedExpression.fun_type_disambig_patttern)
        self.do_disambiguated_id_test('Function.FUN_1()', Function, 'fun_1',
                                      ParsedExpression.fun_type_disambig_patttern, case_fold_match=True)

        self.do_disambiguated_id_error_test(
            'NotFunction.foo()',
            "contains '{}', which doesn't use 'Function' as a disambiguation model type")
        self.do_disambiguated_id_error_test(
            'Function.fun_1',
            "contains '{}', which uses 'Function' as a disambiguation model type but doesn't use Function syntax")
        self.do_disambiguated_id_error_test(
            'NoSuchModel.fun_1',
            "contains '{}', but the disambiguation model type 'NoSuchModel' cannot be referenced by "
            "'RateLawExpression' expressions")
        self.do_disambiguated_id_error_test(
            'Parameter.fun_1',
            "contains '{}', but 'fun_1' is not the id of a 'Parameter'")

        self.do_disambiguated_id_test('Observable.test_id', Observable, 'test_id',
                                      ParsedExpression.model_type_disambig_pattern)
        self.do_disambiguated_id_test('Observable.TEST_ID', Observable, 'test_id',
                                      ParsedExpression.model_type_disambig_pattern, case_fold_match=True)

        # do not find a match
        wc_lang_expr = self.make_wc_lang_expr('3 * 2')
        self.assertEqual(wc_lang_expr.get_disambiguated_id(0), None)

    def do_related_object_id_error_test(self, expr, expected_error):
        wc_lang_expr = self.make_wc_lang_expr(expr)
        result = wc_lang_expr.get_related_obj_id(0)
        self.assertTrue(isinstance(result, str))
        self.assertRegex(result, self.esc_re_center(expected_error))

    def test_related_object_id_errors(self):
        self.do_related_object_id_error_test(
            'x[c]',
            ["contains the identifier(s)", "which aren't the id(s) of an object"])

    def test_related_object_id_mult_matches_error(self):
        del self.objects[Species]
        self.do_related_object_id_error_test(
            'test_id',
            ["multiple model object id matches: 'test_id' as a Observable id, 'test_id' as a Parameter id"])

    def do_related_object_id_test(self, expr, expected_token_string, expected_related_type,
                                  expected_id, pattern, case_fold_match=False):
        wc_lang_expr = self.make_wc_lang_expr(expr)
        lex_match = wc_lang_expr.get_related_obj_id(0, case_fold_match=case_fold_match)
        self.assertTrue(isinstance(lex_match, LexMatch))
        self.assertEqual(lex_match.num_py_tokens, len(pattern))
        self.assertEqual(len(lex_match.wc_tokens), 1)
        wc_token = lex_match.wc_tokens[0]

        self.assertEqual(wc_token,
                         # note: wc_token.model is cheating
                         WcToken(WcTokenCodes.wc_obj_id, expected_token_string,
                                 expected_related_type,
                                 expected_id, wc_token.model))

    def test_related_object_id_matches(self):
        self.do_related_object_id_test('test_id[c] + 3*x', 'test_id[c]', Species, 'test_id[c]',
                                       Species.Meta.token_pattern)
        self.do_related_object_id_test('param_id', 'param_id', Parameter, 'param_id', (token.NAME, ))
        self.do_related_object_id_test('param_iD', 'param_iD', Parameter, 'param_id', (token.NAME, ),
                                       case_fold_match=True)
        self.do_related_object_id_test('PARAM_ID', 'PARAM_ID', Parameter, 'param_id', (token.NAME, ),
                                       case_fold_match=True)

        # no token matches
        wc_lang_expr = self.make_wc_lang_expr("3 * 4")
        self.assertEqual(wc_lang_expr.get_related_obj_id(0), None)

    def do_fun_call_error_test(self, expr, expected_error, obj_type=RateLawExpression):
        wc_lang_expr = self.make_wc_lang_expr(expr, obj_type=obj_type)
        result = wc_lang_expr.get_func_call_id(0)
        self.assertTrue(isinstance(result, str))
        self.assertRegex(result, self.esc_re_center(expected_error))

    def test_fun_call_id_errors(self):
        self.do_fun_call_error_test('foo(3)', ["contains the func name ",
                                               "but it isn't in {}.Meta.valid_functions".format(
                                                   RateLawExpression.__name__)])

        class TestModelExpression(obj_model.Model):
            class Meta(obj_model.Model.Meta):
                valid_models = ('Function',)
        self.do_fun_call_error_test('foo(3)', ["contains the func name ",
                                               "but {}.Meta doesn't define 'valid_functions'".format(
                                                   TestModelExpression.__name__)],
                                    obj_type=TestModelExpression)

    def test_fun_call_id(self):
        wc_lang_expr = self.make_wc_lang_expr('log(3)')
        lex_match = wc_lang_expr.get_func_call_id(0)
        self.assertTrue(isinstance(lex_match, LexMatch))
        self.assertEqual(lex_match.num_py_tokens, len(wc_lang_expr.function_pattern))
        self.assertEqual(len(lex_match.wc_tokens), 2)
        self.assertEqual(lex_match.wc_tokens[0], WcToken(WcTokenCodes.math_fun_id, 'log'))
        self.assertEqual(lex_match.wc_tokens[1], WcToken(WcTokenCodes.op, '('))

        # no token match
        wc_lang_expr = self.make_wc_lang_expr('no_fun + 3')
        self.assertEqual(wc_lang_expr.get_func_call_id(0), None)

    def test_bad_tokens(self):
        rv, errors = ParsedExpression(RateLawExpression, 'test', '+= *= @= : {}', {}).tokenize()
        self.assertEqual(rv, None)
        for bad_tok in ['+=', '*=', '@=', ':', '{', '}']:
            self.assertRegex(errors[0], r'.*contains bad token\(s\):.*' + re.escape(bad_tok) + '.*')
        # test bad tokens that don't have string values
        rv, errors = ParsedExpression(RateLawExpression, 'test', """
 3
 +1""", {}).tokenize()
        self.assertEqual(rv, None)
        self.assertRegex(errors[0], re.escape("contains bad token(s)"))

    def do_tokenize_id_test(self, expr, expected_wc_tokens, expected_related_objs,
                            model_type=RateLawExpression,
                            test_objects=None, case_fold_match=False):
        if test_objects is None:
            test_objects = self.objects_hard
        wc_lang_expr = ParsedExpression(model_type, 'attr', expr, test_objects)
        wc_tokens, related_objects = wc_lang_expr.tokenize(case_fold_match=case_fold_match)
        self.assertEqual(wc_lang_expr.errors, [])
        self.assertEqual(wc_tokens, expected_wc_tokens)
        for obj_types in test_objects:
            if obj_types in expected_related_objs.keys():
                self.assertEqual(related_objects[obj_types], expected_related_objs[obj_types])
            else:
                self.assertEqual(related_objects[obj_types], {})

    def extract_from_objects(self, objects, type_id_pairs):
        d = {}
        for obj_type, id in type_id_pairs:
            if obj_type not in d:
                d[obj_type] = {}
            d[obj_type][id] = objects[obj_type][id]
        return d

    def test_non_identifier_tokens(self):
        expr = ' 7 * ( 5 - 3 ) / 2'
        expected_wc_tokens = [
            WcToken(code=WcTokenCodes.number, token_string='7'),
            WcToken(code=WcTokenCodes.op, token_string='*'),
            WcToken(code=WcTokenCodes.op, token_string='('),
            WcToken(code=WcTokenCodes.number, token_string='5'),
            WcToken(code=WcTokenCodes.op, token_string='-'),
            WcToken(code=WcTokenCodes.number, token_string='3'),
            WcToken(code=WcTokenCodes.op, token_string=')'),
            WcToken(code=WcTokenCodes.op, token_string='/'),
            WcToken(code=WcTokenCodes.number, token_string='2'),
        ]
        self.do_tokenize_id_test(expr, expected_wc_tokens, {})

    def test_tokenize_w_ids(self):
        # test get_related_obj_id
        expr = 'test_id'
        expected_wc_tokens = \
            [WcToken(WcTokenCodes.wc_obj_id, expr, Observable,
                     expr, self.objects_hard[Observable][expr])]
        expected_related_objs = self.extract_from_objects(self.objects_hard, [(Observable, expr)])
        self.do_tokenize_id_test(expr, expected_wc_tokens, expected_related_objs)

        # test get_disambiguated_id
        expr = 'Parameter.duped_id + 2*Observable.duped_id'
        expected_wc_tokens = [
            WcToken(WcTokenCodes.wc_obj_id, 'Parameter.duped_id', Parameter, 'duped_id',
                    self.objects_hard[Parameter]['duped_id']),
            WcToken(WcTokenCodes.op, '+'),
            WcToken(WcTokenCodes.number, '2'),
            WcToken(WcTokenCodes.op, '*'),
            WcToken(WcTokenCodes.wc_obj_id, 'Observable.duped_id', Observable, 'duped_id',
                    self.objects_hard[Observable]['duped_id']),
        ]
        expected_related_objs = self.extract_from_objects(self.objects_hard, [(Parameter, 'duped_id'),
                                                                              (Observable, 'duped_id')])
        self.do_tokenize_id_test(expr, expected_wc_tokens, expected_related_objs)

        # test get_func_call_id
        expr = 'log(3) + fun_2() - Function.Observable()'
        expected_wc_tokens = [
            WcToken(code=WcTokenCodes.math_fun_id, token_string='log'),
            WcToken(WcTokenCodes.op, '('),
            WcToken(WcTokenCodes.number, '3'),
            WcToken(WcTokenCodes.op, ')'),
            WcToken(WcTokenCodes.op, '+'),
            WcToken(WcTokenCodes.wc_obj_id, 'fun_2', Function, 'fun_2',
                    self.objects_hard[Function]['fun_2']),
            WcToken(WcTokenCodes.op, '('),
            WcToken(WcTokenCodes.op, ')'),
            WcToken(WcTokenCodes.op, '-'),
            WcToken(WcTokenCodes.wc_obj_id, 'Function.Observable()', Function, 'Observable',
                    self.objects_hard[Function]['Observable'])
        ]
        expected_related_objs = self.extract_from_objects(self.objects_hard,
                                                          [(Function, 'fun_2'), (Function, 'Observable')])
        self.do_tokenize_id_test(expr, expected_wc_tokens, expected_related_objs)

        # test case_fold_match=True for get_related_obj_id and get_disambiguated_id
        expr = 'TEST_ID - Parameter.DUPED_ID'
        expected_wc_tokens = [
            WcToken(WcTokenCodes.wc_obj_id, 'TEST_ID', Observable, 'test_id',
                    self.objects_hard[Observable]['test_id']),
            WcToken(WcTokenCodes.op, '-'),
            WcToken(WcTokenCodes.wc_obj_id, 'Parameter.DUPED_ID', Parameter, 'duped_id',
                    self.objects_hard[Parameter]['duped_id']),
        ]
        expected_related_objs = self.extract_from_objects(self.objects_hard, [(Parameter, 'duped_id'),
                                                                              (Observable, 'test_id')])
        self.do_tokenize_id_test(expr, expected_wc_tokens, expected_related_objs, case_fold_match=True)

    def test_tokenize_w_multiple_ids(self):
        # at idx==0 match more than one of these get_related_obj_id(), get_disambiguated_id(), get_func_call_id()
        # test get_related_obj_id and get_disambiguated_id'
        test_objects = {
            Parameter: {'Observable': Parameter()},
            Observable: {'test_id': Observable()}
        }
        expr = 'Observable.test_id'
        expected_wc_tokens = [
            WcToken(WcTokenCodes.wc_obj_id, expr, Observable, 'test_id',
                    test_objects[Observable]['test_id'])
        ]
        expected_related_objs = self.extract_from_objects(test_objects, [(Observable, 'test_id')])
        self.do_tokenize_id_test(expr, expected_wc_tokens, expected_related_objs,
                                 test_objects=test_objects)

        # test get_related_obj_id and get_func_call_id'
        test_objects = {
            Parameter: {'Function': Parameter()},
            Function: {'fun_2': Function()}
        }
        expr = 'Function.fun_2()'
        expected_wc_tokens = [
            WcToken(WcTokenCodes.wc_obj_id, expr, Function, 'fun_2',
                    test_objects[Function]['fun_2'])
        ]
        expected_related_objs = self.extract_from_objects(test_objects, [(Function, 'fun_2')])
        self.do_tokenize_id_test(expr, expected_wc_tokens, expected_related_objs,
                                 test_objects=test_objects)

    def do_tokenize_error_test(self, expr, expected_errors, model_type=RateLawExpression, test_objects=None):
        if test_objects is None:
            test_objects = self.objects_hard
        wc_lang_expr = ParsedExpression(model_type, 'attr', expr, test_objects)
        sb_none, errors = wc_lang_expr.tokenize()
        self.assertEqual(sb_none, None)
        # expected_errors is a list of lists of strings that should match the actual errors
        expected_errors = [self.esc_re_center(ee) for ee in expected_errors]
        self.assertEqual(len(errors), len(expected_errors),
                         "Counts differ: num errors {} != Num expected errors {}".format(
            len(errors), len(expected_errors)))
        expected_errors_found = {}
        for expected_error in expected_errors:
            expected_errors_found[expected_error] = False
        for error in errors:
            for expected_error in expected_errors:
                if re.match(expected_error, error):
                    if expected_errors_found[expected_error]:
                        self.fail("Expected error '{}' matches again".format(expected_error))
                    expected_errors_found[expected_error] = True
        for expected_error, status in expected_errors_found.items():
            self.assertTrue(status, "Expected error '{}' not found in errors".format(expected_error))

    def test_tokenize_errors(self):
        bad_id = 'no_such_id'
        self.do_tokenize_error_test(
            bad_id,
            [["contains the identifier(s) '{}', which aren't the id(s) of an object".format(bad_id)]])
        bad_id = 'Observable.no_such_observable'
        self.do_tokenize_error_test(
            bad_id,
            [["contains multiple model object id matches: 'Observable' as a Function id, 'Observable' as a Parameter id"],
             ["contains '{}', but '{}'".format(bad_id, bad_id.split('.')[1]), "is not the id of a"]])
        bad_id = 'no_such_function'
        bad_fn_name = bad_id+'()'
        self.do_tokenize_error_test(
            bad_fn_name,
            [["contains the identifier(s) '{}', which aren't the id(s) of an object".format(bad_id)],
             ["contains the func name '{}', but it isn't in ".format(bad_id), "Meta.valid_functions"]])
        bad_id = 'Function'
        bad_fn_name = bad_id+'.no_such_function2()'
        self.do_tokenize_error_test(
            bad_fn_name,
            [["contains the identifier(s) '{}', which aren't the id(s) of an object".format(bad_id)],
             ["contains '{}', which doesn't refer to a Function".format(bad_fn_name)]])

    def test_str(self):
        expr = 'fun_1() + Parameter.param_id'
        wc_lang_expr = self.make_wc_lang_expr(expr)
        self.assertIn(expr, str(wc_lang_expr))
        self.assertIn('errors: []', str(wc_lang_expr))
        self.assertIn('wc_tokens: []', str(wc_lang_expr))
        wc_lang_expr.tokenize()
        self.assertIn(expr, str(wc_lang_expr))
        self.assertIn('errors: []', str(wc_lang_expr))
        self.assertIn('wc_tokens: [WcToken', str(wc_lang_expr))

    def test_model_class_lacks_meta(self):
        class Foo(object):
            pass
        objects = {
            Foo: {'foo_1': Foo(), 'foo_2': Foo()}
        }
        with self.assertRaisesRegex(ParsedExpressionError,
                                    "model_cls 'Foo' is not a subclass of obj_model.Model"):
            ParsedExpression(Foo, 'expr_attr', '', self.objects)

    def do_test_eval(self, expr, obj_type, related_obj_val, expected_val):
        wc_lang_expr = self.make_wc_lang_expr(expr, obj_type=obj_type)
        wc_lang_expr.tokenize()
        evaled_val = wc_lang_expr.test_eval(val=related_obj_val)
        self.assertEqual(expected_val, evaled_val)

    def test_test_eval(self):
        related_obj_val = 3

        # test combination of WcTokenCodes
        expected_val = 4 * related_obj_val + pow(2, related_obj_val) + related_obj_val
        self.do_test_eval('4 * param_id + pow(2, obs_id) + fun_2()', RateLawExpression,
                          related_obj_val, expected_val)

        # test different model classes
        self.do_test_eval('4 * param_id + pow(2, obs_id) + fun_2()', FunctionExpression,
                          related_obj_val, expected_val)

        # test different exceptions
        # syntax error
        model_type = RateLawExpression
        wc_lang_expr = self.make_wc_lang_expr('4 *', obj_type=model_type)
        wc_lang_expr.tokenize()
        with self.assertRaisesRegex(ParsedExpressionError,
                                    "SyntaxError: cannot eval expression .* in {}".format(
                model_type.__name__)):
            wc_lang_expr.test_eval()

        # expression that could not be serialized
        expr = 'foo(6)'
        wc_lang_expr = self.make_wc_lang_expr(expr, obj_type=model_type)
        wc_lang_expr.tokenize()
        with self.assertRaisesRegex(ParsedExpressionError,
                                    re.escape("cannot evaluate '{}', as it not been "
                                              "successfully tokenized".format(expr))):
            wc_lang_expr.test_eval()


class TestParsedExpressionVerifier(unittest.TestCase):

    def test_expression_verifier(self):

        number_is_good_transitions = [   # (current state, message, next state)
            ('start', (WcTokenCodes.number, None), 'accept'),
        ]
        expression_verifier = ParsedExpressionVerifier('start', 'accept', number_is_good_transitions)
        number_is_good = [
            WcToken(WcTokenCodes.number, '3'),
        ]
        valid, error = expression_verifier.validate(number_is_good)
        self.assertTrue(valid)
        self.assertTrue(error is None)
        # an empty expression is invalid
        valid, error = expression_verifier.validate([])
        self.assertFalse(valid)

    def test_linear_expression_verifier(self):

        valid_linear_expr = [   # id0 - 3*id1 - 3.5*id1 + 3.14e+2*id3
            WcToken(WcTokenCodes.wc_obj_id, 'id0'),
            WcToken(WcTokenCodes.op, '-'),
            WcToken(WcTokenCodes.number, '3'),
            WcToken(WcTokenCodes.op, '*'),
            WcToken(WcTokenCodes.wc_obj_id, 'id1'),
            WcToken(WcTokenCodes.op, '-'),
            WcToken(WcTokenCodes.number, '3.5'),
            WcToken(WcTokenCodes.op, '*'),
            WcToken(WcTokenCodes.wc_obj_id, 'id1'),
            WcToken(WcTokenCodes.op, '+'),
            WcToken(WcTokenCodes.number, '3.14e+2'),
            WcToken(WcTokenCodes.op, '*'),
            WcToken(WcTokenCodes.wc_obj_id, 'id3'),
        ]

        linear_expression_verifier = LinearParsedExpressionVerifier()
        valid, error = linear_expression_verifier.validate(valid_linear_expr)
        self.assertTrue(valid)
        self.assertTrue(error is None)
        # dropping any single token from valid_linear_expr produces an invalid expression
        for i in range(len(valid_linear_expr)):
            valid_linear_expr_without_i = valid_linear_expr[:i] + valid_linear_expr[i+1:]
            valid, error = linear_expression_verifier.validate(valid_linear_expr_without_i)
            self.assertFalse(valid)

        # an empty expression is valid
        valid, error = linear_expression_verifier.validate([])
        self.assertTrue(valid)
        self.assertTrue(error is None)

        invalid_linear_exprressions = [
            [WcToken(WcTokenCodes.math_fun_id, 'log')],     # math functions not allowed
            [WcToken(WcTokenCodes.number, '3j')],           # numbers must be floats
        ]
        for invalid_linear_exprression in invalid_linear_exprressions:
            valid, error = linear_expression_verifier.validate(invalid_linear_exprression)
            self.assertFalse(valid)

        invalid_linear_exprressions = [
            [WcToken(WcTokenCodes.other, ',')],             # other not allowed
        ]
        for invalid_linear_exprression in invalid_linear_exprressions:
            error = linear_expression_verifier.make_dfsa_messages(invalid_linear_exprression)
            self.assertTrue(error is None)
