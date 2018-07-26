# precompiler

Note: this is work in progress...

## Introduction

Similar to the c preprocessor, the precompiler is a processing tool for generic code. However similar, it has much more capability (including recursive macros) that allow you to create more complex behavior. There are a lot of use cases for this that will be covered in some examples.

#### Features:

- Expandable Python api that can be extended and used in build systems
- Support for custom lexers and virtually any language
- Uses with python in conditional check and others commands (example `#run print("hello world")`, `#if python_code("some_string") == True: ...`)
- Recursive macros
- Powerful argument capture for macros


#### Dependencies

- ply

## Quick Example

```
//c++ source file:
#inline "#include <stdio>"
//#define ENABLE_DEBUG_LOG
int main()
{
	#ifdef ENABLE_DEBUG_LOG
		std::cout << "debug mode enabled";
	#else
		std::cout << "release mode";
	#endif

	return 0;
}

//after preprocessing:
#include <stdio>
int main()
{
	std::cout << "release mode enabled";
	return 0;
}
```

```
//glsl source file
#include "metadata.glsl"

varying lowp vec4 v_VertexColor;

#ifdef USE_COLOR
	uniform(lowp,vec4) u_DefaultColor;
	//^ 'uniform' macro can capture identifier 'u_DefaultColor' as argument
#else
	#define u_DefaultColor # 1.0
#endif
void main()
{
	gl_FragColor =  v_VertexColor * u_DefaultColor;
}

//glsl after preprocessing with 'USE_COLOR'
varying lowp vec4 v_VertexColor;
uniform lowp vec4 u_DefaultColor;
void main()
{
	gl_FragColor = v_VertexColor * u_DefaultColor;
}
//also a metadata json can be extracted:
{
	"uniforms" : [
		"u_DefaultColor" : ["lowp","vec4"]
	]
}
```

## Alternatives

https://www.boost.org/doc/libs/1_67_0/libs/preprocessor/doc/index.html

https://gcc.gnu.org/onlinedocs/cpp/

https://www.gnu.org/software/m4/m4.html

http://mcpp.sourceforge.net/

http://math.mit.edu/~auroux/software/gpp.html

## Motivation

In c and c++ the #include system is probably one of the most controvertial feature of the proceprcessor. Misusing it can lead to long compilation times and all sort of compile errors and even crashes (combined with miused defines). That being said the c preprocessor enabled a lot of powerfull features in the code that often don't have alternatives in other laguages (python, javascript, etc), here are some of them:

- Efficent removal of debug code and asserts
- Features that can be turned on/off without affecting the final executable or performance.
- Anti piracy protection.
- Custom syntax that makes writing code easier.
- Meta-data and reflection systems inside the code.
- Custom #pragmas were used to generate multi-threaded code.

Having such a tool available to the developer with even more functionality was the main motivation behind the precompiler. The main goals are: 

- Similar to C precompiler
- Easy to understand
- Allow it to work with any language
- Powerfull and simple code and metdata generation



## Work in progress

The short term todo list:

- Implementation for `#colapse`
- Built-in macros implementation (`__FILE__`, `__LINE__`)
- Tests for all errors
- Tests for complex scenarios (More Tests)
- Proper dependency tree generation
- Examples

## Known issues

- Token line numbers are incorrect.
- Generated files has incorrect spacing.