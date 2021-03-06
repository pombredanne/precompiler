

import precompiler._impl.pc_define as _impl_pc_define
import precompiler._impl.pc_iterator as _impl_pc_iterator
import precompiler._impl.pc_output as _impl_pc_output
import precompiler._impl.pc_default_macros as _pc_macros
import precompiler._utils.pc_utils as _pc_utils


import timeit
import datetime

_token_flags = _pc_utils.token_flags
_primitive_toks = _pc_utils.primitive_tokens
_cmd_tokens = _pc_utils.precompiler_tokens

##########################################################################################################

# parser state that reads expanded define arguments
class _pc_argument_parser(_impl_pc_iterator.PrecompilerExecController):
	def __init__(self,vm,parent_state,source_define,expanded_token):
		_impl_pc_iterator.PrecompilerExecController.__init__(self,vm)
		self.parent_state = parent_state
		self.define = source_define
		self.expanded_token = expanded_token

		self.scope_stack = []

		self.next_arguments = source_define.GetRequiredArguments().copy()

		self.target_argument_name = None
		self.target_aquired_content = False

		self.arg_map = {}

		self._shift_first()

	def push_to_argument(self,tok):

		#we must have an argument assigned here
		if self.target_argument_name == None:
			lh = self._get_look_ahead_arg_token()
			assert lh != None, "Missing lookahead token!"
			(_,_,expected_value,_) = lh
			self.precompiler.RaiseErrorOnToken(tok,"Invalid arguments!","Expected [" + expected_value[0] + "]")

		self.arg_map[self.target_argument_name].append(tok)

		(tok_flags,tok_type,val,_) = tok

		#measure non important tokens
		if (tok_type != _primitive_toks.kWhitespace) and (tok_type != _primitive_toks.kWhitespace):
			self.target_aquired_content = True #added one more argument

		if tok_type == _cmd_tokens.k_scope_push:
			self.scope_stack.append(tok_flags)
		elif tok_type == _cmd_tokens.k_scope_pop:
			if len(self.scope_stack) == 0:
				self.precompiler.RaiseErrorOnToken(tok,"Unexpected token!","[" + val[0] + "]")
			if (self.scope_stack[-1] & _token_flags.k_first_mask) != (tok_flags & _token_flags.k_first_mask):
				self.precompiler.RaiseErrorOnToken(tok,"Mismatched token!","[" + val[0] + "]")
			self.scope_stack.pop()


	def _get_look_ahead_arg_token(self):
		if len(self.scope_stack) > 0:
			return None
		if len(self.next_arguments) == 0:
			return None
		return self.next_arguments[0]

	def _shift_first(self):
		while len(self.next_arguments) > 0:
			(_,expected_type,expected_value,_) = self.next_arguments[0]
			if expected_type != _primitive_toks.kIdentifier:
				break;

			self.target_argument_name = expected_value[0]
			self.target_aquired_content = False

			self.arg_map.setdefault(expected_value[0],[])
			self.next_arguments.pop(0)

	def shift(self):
		self.target_argument_name = None
		self.target_aquired_content = False
		self.next_arguments.pop(0)
		self._shift_first()

	def get_exit_state(self):
		if len(self.next_arguments) == 0 and len(self.scope_stack) == 0:
			#we are done parsing arguments, expand macro and exit
			self.precompiler._expand_define_with_evaluation(self.expanded_token,self.define,self.arg_map)
			return self.parent_state
		return self

	def Advance(self,tok):

		(_,toktype,value,_) = tok

		lh = self._get_look_ahead_arg_token()

		if lh == None:
			#last token from arg list, push to argument and than exit
			self.push_to_argument(tok)
			if(self.target_aquired_content == False):
				return self #because we did not get any valuable content, we wait 

		else:
			(_,expected_type,expected_value,_) = lh

			if toktype == expected_type and value == expected_value:
				#if we match the expected stuff we advance to next one
				self.shift()
			else:
				self.push_to_argument(tok)

		return self.get_exit_state()


	def Finish(self):
		self.precompiler.RaiseErrorOnToken(self.source_token,"Incomplete arguments",None)

##########################################################################################################

# global state parser. works with the vm states also
class _pc_root_parser(_impl_pc_iterator.PrecompilerExecController):
	def __init__(self,vm,builder):
		_impl_pc_iterator.PrecompilerExecController.__init__(self,vm)

		self.assembler = builder

	def Finish(self):
		self.assembler.Close()


	def _create_file_info(self,tok):
		_fi = self.precompiler.file_interface
		active_file_path = self.precompiler.input_state.GetActiveSourceFile()
		file_handle = _fi.GetOrLoadFile(active_file_path)
		lines = [
			"--------------------------------------------------------------------------------------------------------------------------------------------",
			"-- ! Preprocessed file, CHANGES WILL BE DISCARDED ! ----------------------------------------------------------------------------------------",
			"--------------------------------------------------------------------------------------------------------------------------------------------",
			"-- Time: " + _pc_utils.GetNowTimeString(),
			"-- Src path: " + active_file_path,
			"-- Preprocessor version:" + str(_pc_macros._PCVER_HIGH_) + "." + str(_pc_macros._PCVER_LOW0_) + "." + str(_pc_macros._PCVER_LOW1_),
			"--------------------------------------------------------------------------------------------------------------------------------------------"
		]
		return "\n".join([_fi.CreateOutputComment(l) for l in lines]);

	def _evaluate_source_id(self,tok,_id):
		if _id == 'once':
			source_file = self.precompiler.input_state.GetActiveSourceFile()
			self.precompiler.file_interface.StashFileContent(source_file)
		elif _id == 'dup':
			source_file = self.precompiler.input_state.GetActiveSourceFile()
			self.precompiler.file_interface.StashFileContent(source_file)
		elif _id == 'break':
			self.precompiler._break_file_unit();
		elif _id == 'info':
			file_info = self._create_file_info(tok);
			self.assembler.Write((_token_flags.k_trivial_flag,_primitive_toks.kInlined,[file_info],_pc_utils.TokSource(tok)))
		else:
			self.precompiler.RaiseErrorOnToken(tok,"Unknown #source token!","Value `" + _id + "`")

	def _evaluate_functions_with_string_arg(self,tok,toktype,unboxed_str):

		if toktype == _cmd_tokens.k_include:
			self.precompiler.open_file_and_include(unboxed_str,tok)
		elif toktype == _cmd_tokens.k_inline_include:
			self.assembler.Write((_token_flags.k_trivial_flag,_primitive_toks.kInlined,[self.precompiler.open_file_and_get_str(unboxed_str,tok)],_pc_utils.TokSource(tok)))
		elif toktype == _cmd_tokens.k_inline_str:
			self.assembler.Write((_token_flags.k_trivial_flag,_primitive_toks.kInlined,[unboxed_str],_pc_utils.TokSource(tok)))
		elif toktype == _cmd_tokens.k_error:
			self.precompiler.RaiseErrorOnToken(tok,"User #error!",unboxed_str)
		else:
			assert False, "Internal Error"

		return self

	def _expand_define(self,def_inst,tok):
		if def_inst.GetRequiredArguments() != None:
			result = _pc_argument_parser(self.precompiler,self,def_inst,tok)
			return result
		else:
			self.precompiler._expand_define_with_evaluation(tok,def_inst,None)
			return self

	def _end_colapse(self):
		next_assembler = self.assembler.NextAssembler()
		assert next_assembler != None, "Internal error on _end_colapse"
		self.assembler.Close()
		self.assembler = next_assembler

	def _colapse_macro(self,tok):
		_tok_value = tok[2]
		df = self.precompiler.get_required_define(tok,_tok_value[1])

		if df.IsBuiltin() == True:
			self.precompiler.RaiseErrorOnToken(tok,"#colapse does not work on builtin macros!",df.name)
		if df.GetRequiredArguments() != None:
			self.precompiler.RaiseErrorOnToken(tok,"#colapse does not work on macros that require arguments!",df.name)

		tokens = df.GetValueAsTokens(tok)
		df.ClearValue();

		self.assembler = _impl_pc_output.VarDefineValueAssembler(df).SetNextAssembler(self.assembler)
		self.precompiler.open_colapse(_impl_pc_iterator.ColapsedTokenInterator(tok,tokens,self.precompiler))

	def _run_command(self,tok,inline_content):
		result = self.precompiler._evaluate_tok(tok);
		if(result != None):
			if inline_content == True:
				self.assembler.Write((_token_flags.k_trivial_flag,_primitive_toks.kInlined,[str(result)],_pc_utils.TokSource(tok)))
			else:
				#todo: make function in pre
				tokens = self.precompiler.file_interface.RetokenizeContent(str(result),tok)
				next_iterator = _impl_pc_iterator.GeneratedTokenInterator(tokens)

				if self.precompiler.input_state.PushState(next_iterator,None) == False:
					self.precompiler.RaiseErrorOnToken(tok,"Stack overflow while executin #run!",None)

	def Advance(self,tok):

		_prep = self.precompiler

		_is_executed = _prep.is_evaluating() #true/false if the

		tokflags = tok[0]

		#strings, characters, comments, whitespaces, etc
		if (tokflags & _token_flags.k_trivial_flag) != 0:
			if _is_executed:

				self.assembler.Write(tok)
			return self

		toktype = tok[1]
		_tok_value = tok[2]

		#check for defines with same name
		if toktype == _primitive_toks.kIdentifier:
			if _is_executed:
				df = _prep.input_state.FindVarDefineWithName(_tok_value[0])
				if df != None:
					return self._expand_define(df,tok)
				else:
					self.assembler.Write(tok)
			return self

		#conditional tokens, no output
		if (tokflags & _token_flags.k_conditional_flag) != 0:
			if toktype == _cmd_tokens.k_if_defined:
				if _is_executed:
					_prep.push_execution_state(_prep.is_defined(_tok_value[1]))
				else:
					_prep.push_execution_state(None)
			elif toktype == _cmd_tokens.k_if_not_defined:
				if _is_executed:
					cond = _prep.is_defined(_tok_value[1])
					_prep.push_execution_state(True if (cond == False) else False)
				else:
					_prep.push_execution_state(None)
			elif toktype == _cmd_tokens.k_if:
				if _prep.is_evaluating():
					_prep.push_execution_state(_prep.evaluate_if_condition(tok))
				else:
					_prep.push_execution_state(None)
			elif toktype == _cmd_tokens.k_else_if:
				_prep.negate_execution_state(tok)
				if _prep.is_evaluating():
					_prep.pop_execution_state(tok)
					_prep.push_execution_state(_prep.evaluate_if_condition(tok))
				else:
					_prep.pop_execution_state(tok)
					_prep.push_execution_state(None)
			elif toktype == _cmd_tokens.k_else:
				_prep.negate_execution_state(tok)
			elif toktype == _cmd_tokens.k_endif:
				_prep.pop_execution_state(tok)

			#end of conditional
			return self

		#non conditionals statements, no output
		if _is_executed:
			#all this commands should have k_command_flag
			if (tokflags & _token_flags.k_id_str_argument_flag) != 0:
				(_,name_or_str,type_of_argument) = _tok_value

				if type_of_argument == _token_flags.k_identifier_flag:
					string_value = _prep.get_required_define(tok,name_or_str).GetValueAsString(tok)
					return self._evaluate_functions_with_string_arg(tok,toktype,string_value)

				elif type_of_argument == _token_flags.k_string_flag:
					return self._evaluate_functions_with_string_arg(tok,toktype,_pc_utils.UnboxString(name_or_str))

			elif toktype == _cmd_tokens.k_define:
				(_,name,content) = _tok_value
				(arguments,value) = _prep.parse_define_content(tok,content);
				if (tokflags & _token_flags.k_no_error) != 0:
					_prep.add_new_define(tok,_impl_pc_define.VarDefine(name,arguments,value,tok,_prep),False)
				else:
					_prep.add_new_define(tok,_impl_pc_define.VarDefine(name,arguments,value,tok,_prep),True)

			elif toktype == _cmd_tokens.k_colapse:
				self._colapse_macro(tok)

			elif toktype == _cmd_tokens.k_run:
				self._run_command(tok,False)
			elif toktype == _cmd_tokens.k_inline_eval:
				self._run_command(tok,True)

			elif toktype == _cmd_tokens.k_cwstrip:
				_prep.get_required_define(tok,_tok_value[1]).CwStrip()

			elif toktype == _cmd_tokens.k_undefine:
				if _prep.input_state.RemoveDefineRecursive(_tok_value[1]) == False:
					_prep.RaiseErrorOnToken(tok,"Failed to execute #undef statement!","Searching for `" + tok[2] + "`")
			elif toktype == _cmd_tokens.k_source:
				self._evaluate_source_id(tok,_tok_value[1])

			return self

		elif (tokflags & _token_flags.k_command_flag) != 0:
			#cmd tokens that are on a not evaluated, are skipped
			return self

		#should never reach this place
		assert False, "Internal execution error!"


##########################################################################################################
##########################################################################################################

#Main vm processing functions
class _precompiler_backend(object):
	def __init__(self, user_file_handler, options):

		self.parser_state = None #token processor and writer
		self.input_state = None #input reader

 		#if/else state
		self.active_condition = None
		self.condition_stack = []

		#reading and writing files
		self.file_interface = user_file_handler

		self.options = options if options != None else {}

		#eval and if eval context
		self.eval_user_context = self.options.get("EvalContext",None)

		self._cached_eval_tok = None
		self._cached_eval_ctx = None

		self._default_macros = None

		self._dependency_list = None
		if self.options.get("MakeDependencyTree",False) == True:
			self._dependency_list = []


	def push_execution_state(self,is_condition_true):
		self.condition_stack.append(is_condition_true)
		self.active_condition = None

	def negate_execution_state(self,tok):
		if len(self.condition_stack) == 0:
			self.RaiseErrorOnToken(tok,"Unexpected #else statement!",None)

		if self.condition_stack[ -1 ] == True:
			self.condition_stack[ -1 ] = False
		elif self.condition_stack[ -1 ] == False:
			self.condition_stack[ -1 ] = True

		self.active_condition = None

	def pop_execution_state(self,tok):
		if len(self.condition_stack) == 0:
			self.RaiseErrorOnToken(tok,"Unexpected #end! statement",None)
		self.condition_stack.pop()
		self.active_condition = None

	def is_evaluating(self):
		if self.active_condition is None:
			self.active_condition = True
			for x in self.condition_stack:
				if x != None:
					self.active_condition = self.active_condition and x
				else:
					self.active_condition = False
					break

		return self.active_condition

	def _invalidate_eval_ctx(self):
		self._cached_eval_ctx = None

	def prepare_eval_context(self,tok):
		self._cached_eval_tok = tok
		if self._cached_eval_ctx != None:
			return self._cached_eval_ctx

		self._cached_eval_ctx = {}
		self._cached_eval_ctx["defined"] = lambda name_str: self.is_defined(name_str)
		self._cached_eval_ctx["value"] = lambda name_str: self._ev_value(name_str)
		self._cached_eval_ctx["tokens"] = lambda name_str: self._ev_tokens(name_str)

		if self.eval_user_context != None:
			self._cached_eval_ctx.update(self.eval_user_context)

		return self._cached_eval_ctx

	def _ev_tok(self):
		return self._cached_eval_tok

	def _ev_value(self,name):
		et = self._ev_tok()
		return self.get_required_define(et,name).GetValueAsString(et);

	def _ev_tokens(self,name):
		et = self._ev_tok()
		return self.get_required_define(et,name).GetValueAsTokens(et);


	def run_python_eval(self,tok,raw_code):
		eval_ctx = self.prepare_eval_context(tok)

		try:
			#the context is passed as local because we don't want it to be poluted by `eval` function
			result = eval(raw_code,None,eval_ctx)
			return result
		except SyntaxError as e:
			self.RaiseErrorOnToken(tok,"SyntaxError!",str(e))
		except ZeroDivisionError as e:
			self.RaiseErrorOnToken(tok,"ZeroDivisionError!",str(e))
		except NameError as e:
			self.RaiseErrorOnToken(tok,"NameError!",str(e))
		except TypeError as e:
			self.RaiseErrorOnToken(tok,"TypeError!",str(e))

	def evaluate_if_condition(self,tok):
		_tok_value = tok[2]
		result = self.run_python_eval(tok,_tok_value[1]);
		if result == "True":
			return True
		elif result == "False":
			return False
		else:
			try:
				v = int(result)
				if v != 0:
					return True
				return False
			except ValueError:
				return False

		return False

	def open_colapse(self,token_iterator):
		self.input_state.PushState(token_iterator,None)

	def close_colapse(self,original_token):
		if isinstance(self.parser_state,_pc_argument_parser):
			self.RaiseErrorOnToken(original_token,"#colapse requires some arguments for a macro",None)

		self.parser_state._end_colapse()


	def get_required_define(self,tok,define_name):
		result = self.input_state.FindVarDefineWithName(define_name)
		if result == None:
			self.RaiseErrorOnToken(tok,"No define found!","Search name [" + define_name + "]")

		return result

	def is_defined(self,name):
		if self.input_state.FindVarDefineWithName(name) != None:
			return True
		return False

	def add_new_define(self,def_token,def_instance,fail_if_defined):
		if self.input_state.FindVarDefineWithName(def_instance.name) != None:
			if(fail_if_defined == True):
				self.RaiseErrorOnToken(def_token,"Redefinition is not allowed!","Define name: `" + def_instance.name + "`")
			self.input_state.RemoveDefineRecursive(def_instance.name)

		self.input_state.AddGlobalDefine(def_instance)

	def evaluate_file_path(self,strval,tok):
		current_compilation_unit = self.input_state.GetActiveSourceFile()
		abs_path = self.file_interface.FindFileWithPath(strval,current_compilation_unit)
		if abs_path == None:
			self.RaiseErrorOnToken(tok,"Could not locate file!","Path: `" + strval + "`")
		return abs_path

	def open_file_and_get_str(self,strval,tok):
		abs_file_path = self.evaluate_file_path(strval,tok)
		return self.file_interface.GetFileStr(abs_file_path)

	def _break_file_unit(self):
		self.condition_stack = self.input_state.BreakFileUnit();
		self.active_condition = None

	def open_file_and_include(self,strval,tok):

		abs_file_path = self.evaluate_file_path(strval,tok)

		depdendency_handle = self.file_interface.GetOrLoadFile(abs_file_path)
		content = depdendency_handle.tokens()

		if self._dependency_list != None:
			self._dependency_list.append((self.input_state.GetActiveSourceFile(),abs_file_path,depdendency_handle.hash()))

		if self.options.get("SourceOnceByDefault",False) == True:
			self.file_interface.StashFileContent(abs_file_path)

		push_result = self.input_state.PushState(_impl_pc_iterator.FileTokenInterator(content,abs_file_path,self.condition_stack.copy()),None)
		if push_result == False:
			self.RaiseErrorOnToken(tok,"Stack overflow!","Current include `" + abs_file_path + "`.")

	def _evaluate_tok(self,tok):
		_tok_value = tok[2]
		return self.run_python_eval(tok,_tok_value[1]);

	def _expand_define_with_evaluation(self,expanded_tok,def_to_expand,arg_map):
		next_define_map = None
		tokens = def_to_expand.GetValueAsTokens(expanded_tok)

		if arg_map != None:
			next_define_map = _impl_pc_define.VarDefineMap()
			for (name,toklist) in arg_map.items():
				arg_def = _impl_pc_define.VarDefineStatic(name,toklist,expanded_tok,self)
				next_define_map.TryAddLocalDefine(arg_def)

		next_iterator = _impl_pc_iterator.GeneratedTokenInterator(tokens)

		if self.input_state.PushState(next_iterator,next_define_map) == False:
			self.RaiseErrorOnToken(expanded_tok,"Stack overflow while expanding identifier!",None)

	def parse_define_content(self,tok,content):
		if content == None or content == "":
			return (None,[])

		token_list = self.file_interface.RetokenizeContent(content,tok)

		first_list = []
		second_list = None

		split_lists = False
		for ( tok_flags, tok_tp, tok_value, tok_loc ) in token_list:
			if (tok_flags & _token_flags.k_blank) != 0:
				#encountered blank
				if split_lists == False:
					#first blank
					split_lists = True
					second_list = []
					continue;

			if split_lists == False:
				#no blank separator encountered
				first_list.append(( tok_flags, tok_tp, tok_value, tok_loc ))
			else:
				second_list.append(( tok_flags, tok_tp, tok_value, tok_loc ))

		if second_list == None:
			return (None,first_list)
		if len(first_list) == 0:
			return (None,second_list)

		arg_list = [( tok_flags, tok_tp, tok_value, tok_loc ) for ( tok_flags, tok_tp, tok_value, tok_loc ) in first_list if tok_tp != _primitive_toks.kWhitespace or (tok_flags & _token_flags.k_impostor) != 0]

		return (arg_list,second_list)

	def _add_builtin_macro(self,mc):
		self._default_macros[mc.name] = mc
		self.input_state.AddGlobalDefine(mc)

	def init_default_macros(self):
		if self._default_macros != None:
			return
		self._default_macros = {}
		self._add_builtin_macro(_pc_macros.macro__FILE__(self))
		self._add_builtin_macro(_pc_macros.macro__FILENAME__(self))
		self._add_builtin_macro(_pc_macros.macro__FILEROOT__(self))
		self._add_builtin_macro(_pc_macros.macro__PCVER__(self))
		self._add_builtin_macro(_pc_macros.macro__PCVER_HIGH__(self))
		self._add_builtin_macro(_pc_macros.macro__PCVER_LOW__(self))
		self._add_builtin_macro(_pc_macros.macro__LINE__(self))
		self._add_builtin_macro(_pc_macros.macro__NOW_TIME__(self))


	def RaiseErrorOnToken(self,tok_tuple,message,variable_message):
		_pc_utils.RaiseErrorAtToken(tok_tuple,message,variable_message)

##########################################################################################################
###########################################################################################################
