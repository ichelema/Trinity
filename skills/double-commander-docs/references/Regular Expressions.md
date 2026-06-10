---
title: 2.14. Syntax of Regular Expressions
source: regexp.html
tags: [doublecmd, documentation]
---

# 2.14. Syntax of Regular Expressions

## Content

- 1. [[Regular Expressions#1. Introduction|Introduction]]
- 2. [[Regular Expressions#2. Simple matches|Simple matches]]
- 3. [[Regular Expressions#3. Escape sequences|Escape sequences]]
- 4. [[Regular Expressions#4. Character classes|Character classes]]
- 5. [[Regular Expressions#5. Metacharacters|Metacharacters]]
  - 5.1. [[Regular Expressions#5.1. Metacharacters - line separators|Metacharacters - line separators]]
  - 5.2. [[Regular Expressions#5.2. Metacharacters - predefined classes|Metacharacters - predefined classes]]
  - 5.3. [[Regular Expressions#5.3. Metacharacters - word boundaries|Metacharacters - word boundaries]]
  - 5.4. [[Regular Expressions#5.4. Metacharacters - iterators|Metacharacters - iterators]]
  - 5.5. [[Regular Expressions#5.5. Metacharacters - alternatives|Metacharacters - alternatives]]
  - 5.6. [[Regular Expressions#5.6. Metacharacters - subexpressions|Metacharacters - subexpressions]]
  - 5.7. [[Regular Expressions#5.7. Metacharacters - backreferences|Metacharacters - backreferences]]
- 6. [[Regular Expressions#6. Assertions (lookahead and lookbehind assertions)|Assertions (lookahead and lookbehind assertions)]]
- 7. [[Regular Expressions#7. Non-capturing groups|Non-capturing groups]]
- 8. [[Regular Expressions#8. Atomic groups|Atomic groups]]
- 9. [[Regular Expressions#9. Unicode categories|Unicode categories]]
- 10. [[Regular Expressions#10. Modifiers|Modifiers]]

Double Commander uses the free library [TRegExpr](https://regex.sorokin.engineer/en/latest/) by Andrey Sorokin.

Most of the explanations are from the help file for this library.

## 1. Introduction

Regular Expressions are a widely-used method of specifying patterns of text to search for. Special characters (**metacharacters**) allow us to specify, for instance, that a particular string we are looking for occurs at the beginning or end of a line, or contains **n** recurrences of a certain character or group of characters.

Double Commander supports regular expressions in the following functions:

- [[Find Files|Find files]] (file names or content search)
- In the [[Multi-Rename Tool]]
- In the internal editor
- In the internal viewer

The TRegExp library supports two modes of operation: ANSI and Unicode. When searching in text files, Double Commander uses both (depending on the file encoding). When searching by name, Unicode is used.

## 2. Simple matches

Any single character matches itself, unless it is a metacharacter with a special meaning described below.

A series of characters matches that series of characters in the target string, so the pattern `bluh` would match `bluh` in the target string.

We can cause characters that normally function as metacharacters or **escape sequences** to be interpreted literally by "escaping" them by preceding them with a backslash `\`, for instance: metacharacter `^` match beginning of string, but `\^` match character `^`, `\\` match `\` and so on.

Here are some examples:

| Example of simple match |  |
| --- | --- |
| Expression | Result |
| foobar | matches string `foobar` |
| \^FooBarPtr | matches `^FooBarPtr` |

## 3. Escape sequences

Characters may be specified using a escape sequences syntax much like that used in C and Perl: `\n` matches a newline, `\t` a tab, etc.

More generally, `\xnn`, where `nn` is a string of hexadecimal digits, matches the character whose ASCII value is `nn`.

If you need wide (Unicode) character code, you can use `\x{nnnn}`, where `nnnn` – one or more hexadecimal digits.

| Escape sequences |  |
| --- | --- |
| Expression | Result |
| \xnn | char with hex code `nn` |
| \x{nnnn} | char with hex code `nnnn` (one byte for plain text and two bytes for Unicode) |
| \t | tab (HT/TAB), same as `\x09` |
| \n | newline (NL/LF), same as `\x0a` |
| \r | carriage return (CR), same as `\x0d` |
| \f | form feed (FF), same as `\x0c` |
| \a | alarm (bell) (BEL), same as `\x07` |
| \e | escape (ESC), same as `\x1b` |

Here are some examples:

| Example of escape sequences |  |
| --- | --- |
| Expression | Result |
| foo\x20bar | matches `foo bar` (note space in the middle) |
| \tfoobar | matches `foobar` predefined by tab |

## 4. Character classes

You can specify a character class, by enclosing a list of characters in `[]`, which will match any **one** character from the list.

If the first character after the `[` is `^`, the class matches any character **not** in the list.

Within a list, the `-` character is used to specify a **range**, so that `a-z` represents all characters between `a` and `z`, inclusive.

If you want `-` itself to be a member of a class, put it at the start or end of the list, or escape it with a backslash.

If you want `]` you may place it at the start of list or escape it with a backslash.

| Character classes |  |
| --- | --- |
| Expression | Result |
| [-az] | matches `a`, `z` and `-` |
| [az-] | matches `a`, `z` and `-` |
| [a\-z] | matches `a`, `z` and `-` |
| [a-z] | matches all twenty six small characters from `a` to `z` |
| [\n-\x0D] | matches any of `\x10`, `\x11`, `\x12`, `\x13` |
| [\d-t] | matches any digit, `-` or `t` |
| []-a] | matches any char from `]`..`a` |

Here are some examples:

| Example of character classes |  |
| --- | --- |
| Expression | Result |
| foob[aeiou]r | finds strings `foobar`, `foober` etc. but not `foobbr`, `foobcr` etc. |
| foob[^aeiou]r | find strings `foobbr`, `foobcr` etc. but not `foobar`, `foober` etc. |

## 5. Metacharacters

Metacharacters are special characters which are the essence of Regular Expressions.

There are different types of metacharacters, described below.

## 5.1. Metacharacters - line separators

Some expressions help to detect line separation.

| Line separators |  |
| --- | --- |
| Expression | Result |
| ^ | start of line |
| $ | end of line |
| \A | start of text |
| \Z | end of text |
| . | any character in line |

Here are some examples:

| Example with line separators |  |
| --- | --- |
| Expression | Result |
| ^foobar | matches string `foobar` only if it's at the beginning of line |
| foobar$ | matches string `foobar` only if it's at the end of line |
| ^foobar$ | matches string `foobar` only if it's the only string in line |
| foob.r | matches strings like `foobar`, `foobbr`, `foob1r` and so on |

The `^` metacharacter by default is only guaranteed to match at the beginning of the input string/text, the `$` metacharacter only at the end. Embedded line separators will not be matched by `^` or `$`.

You may, however, wish to treat a string as a multi-line buffer, such that the `^` will match after any line separator within the string, and `$` will match before any line separator. You can do this by switching On the [[Regular Expressions#10. Modifiers|modifier m]].

The `\A` and `\Z` are just like `^` and `$`, except that they won't match multiple times when the [[Regular Expressions#10. Modifiers|modifier m]] is used, while `^` and `$` will match at every internal line separator.

The `.` metacharacter by default matches any character, but if you switch Off the [[Regular Expressions#10. Modifiers|modifier s]], then `.` won't match embedded line separators.

TRegExpr works with line separators as recommended at Unicode technical standards ([Technical Standard #18](https://www.unicode.org/reports/tr18/)):

- `^` is at the beginning of a input string, and, if [[Regular Expressions#10. Modifiers|modifier m]] is On, also immediately following any occurrence of `\x0D\x0A` or `\x0A` or `\x0D` (with Unicode support: also `\x2028` or `\x2029` or `\x0B` or `\x0C` or `\x85`). Note that there is no empty line within the sequence `\x0D\x0A`.
- `$` is at the end of a input string, and, if [[Regular Expressions#10. Modifiers|modifier m]] is On, also immediately preceding any occurrence of `\x0D\x0A` or `\x0A` or `\x0D` (with Unicode support: also `\x2028` or `\x2029` or `\x0B` or `\x0C` or `\x85`). Note that there is no empty line within the sequence `\x0D\x0A`.
- `.` matches any character, but if you switch Off [[Regular Expressions#10. Modifiers|modifier s]] then `.` doesn't match `\x0D\x0A` and `\x0A` and `\x0D` (with Unicode support: also `\x2028` and `\x2029` and `\x0B` and `\x0C` and `\x85`).

Note that `^.*$` (an empty line pattern) does not match the empty string within the sequence `\x0D\x0A`, but matches the empty string within the sequence `\x0A\x0D`.

## 5.2. Metacharacters - predefined classes

Some expressions help to detect group of characters.

| Predefined classes |  |
| --- | --- |
| Expression | Result |
| \w | an alphanumeric character (including `_`), i.e. `[0-9A-Za-z_]` |
| \W | a nonalphanumeric |
| \d | a numeric character |
| \D | a non-numeric |
| \s | any space (same as `[ \t\n\r\f]`) |
| \S | a non space |

You may use `\w`, `\d` and `\s` within custom **character classes**.

Here are some examples:

| Example of predefined classes |  |
| --- | --- |
| Expression | Result |
| foob\dr | matches strings like `foob1r`, `foob6r` and so on but not `foobar`, `foobbr` and so on |
| foob[\w\s]r | matches strings like `foobar`, `foob r`, `foobbr` and so on but not `foob=r` and so on |

## 5.3. Metacharacters - word boundaries

A word boundary (`\b`) is a spot between two characters that has a `\w` on one side of it and a `\W` on the other side of it (in either order), counting the imaginary characters off the beginning and end of the string as matching a `\W`.

| Word boundaries |  |
| --- | --- |
| Expression | Result |
| \b | match a word boundary |
| \B | match a non-(word boundary) |

## 5.4. Metacharacters - iterators

Any item of a regular expression may be followed by another type of metacharacters – iterators.

Using these metacharacters you can specify the number of occurrences of the previous character, metacharacter or subexpression.

| Iterators |  |
| --- | --- |
| Expression | Result |
| * | zero or more ("greedy"), similar to `{0,}` |
| + | one or more ("greedy"), similar to `{1,}` |
| ? | zero or one ("greedy"), similar to `{0,1}` |
| {n} | exactly `n` times ("greedy") |
| {n,} | at least `n` times ("greedy") |
| {n,m} | at least `n` but not more than `m` times ("greedy") |
| *? | zero or more ("non-greedy"), similar to `{0,}?` |
| +? | one or more ("non-greedy"), similar to `{1,}?` |
| ?? | zero or one ("non-greedy"), similar to `{0,1}?` |
| {n}? | exactly `n` times ("non-greedy") |
| {n,}? | at least `n` times ("non-greedy") |
| {n,m}? | at least `n` but not more than `m` times ("non-greedy") |

So, digits in curly brackets of the form `{n,m}`, specify the **minimum** number of times to match the item `n` and the **maximum** `m`.

The form `{n}` is equivalent to `{n,n}` and matches exactly `n` times.

The form `{n,}` matches `n` or more times.

There is no limit to the size of `n` or `m`, but large numbers will slow down execution and chew up more memory.

If a curly bracket occurs in any other context, it is treated as a regular character.

Here are some examples:

| Example of iterators |  |
| --- | --- |
| Expression | Result |
| foob.*r | matches strings like `foobar`, `foobalkjdflkj9r` and `foobr` |
| foob.+r | matches strings like `foobar`, `foobalkjdflkj9r` but not `foobr` |
| foob.?r | matches strings like `foobar`, `foobbr` and `foobr` but not `foobalkj9r` |
| fooba{2}r | matches the string `foobaar` |
| fooba{2,}r | matches strings like `foobaar`, `foobaaar`, `foobaaaar` etc. |
| fooba{2,3}r | matches strings like `foobaar`, or `foobaaar` but not `foobaaaar` |

A little explanation about "greediness".

"Greedy" takes as many as possible, "non-greedy" takes as few as possible.

For example, `b+` and `b*` applied to string `abbbbc` return `bbbb`, `b+?` returns `b`, `b*?` returns empty string, `b{2,3}?` returns `bb`, `b{2,3}` returns `bbb`.

You can switch all iterators into "non-greedy" mode (see the [[Regular Expressions#10. Modifiers|modifier g]]).

## 5.5. Metacharacters - alternatives

You can specify a series of **alternatives** for a pattern using `|` to separate them, so that `fee|fie|foe` will match any of `fee`, `fie`, or `foe` in the target string (as would `f(e|i|o)e`).

The first alternative includes everything from the last pattern delimiter (`(`, `[`, or the beginning of the pattern) up to the first `|`, and the last alternative contains everything from the last `|` to the next pattern delimiter.

For this reason, it's common practice to include alternatives in parentheses, to minimize confusion about where they start and end.

Alternatives are tried from left to right, so the first alternative found for which the entire expression matches, is the one that is chosen.

This means that alternatives are not necessarily greedy.

For example: when matching `foo|foot` against `barefoot`, only the `foo` part will match, as that is the first alternative tried, and it successfully matches the target string. (This might not seem important, but it is important when you are capturing matched text using parentheses.)

Also remember that `|` is interpreted as a literal within square brackets, so if you write `[fee|fie|foe]` you're really only matching `[feio|]`.

Example:

| Example of alternatives |  |
| --- | --- |
| Expression | Result |
| foo(bar\|foo) | matches strings `foobar` or `foofoo` |

## 5.6. Metacharacters - subexpressions

The bracketing construct `( ... )` may also be used for define regular expression subexpressions.

After search you can call any subexpression, also you can use subexpressions as masks.

Subexpressions are numbered based on the left to right order of their opening parenthesis.

First subexpression has number 1, up to 90 subexpressions are supported (whole regular expression match has number 0 – you can substitute it as `$0` or `$&`).

Here are some examples:

| Subexpressions |  |
| --- | --- |
| Expression | Result |
| (foobar){8,10} | matches strings which contain 8, 9 or 10 instances of the `foobar` |
| foob([0-9]\|a+)r | matches `foob0r`, `foob1r` , `foobar`, `foobaar`, `foobaar` etc. |

**Notes about "Replace with" templates:**

- If you want to place raw `$` or `\` into template, then use prefix `\`.
  Example: `1\$ is $2\\rub\\` will return `1$ is <subexpr2>\rub\`.
- If you want to place raw digit after `$n`, then you must delimit `n` with curly braces `{}`.
  For example, `a$12bc` will return `a<subexpr12>bc`, but `a${1}2bc` will return `a<subexpr1>2bc`.

Example:

Let's invert date `21.01.2018` > `2018.01.21`:
 search for: `(\d{2})\.(\d{2})\.(\d{4})`
 replace with: `$3.$2.$1`

## 5.7. Metacharacters - backreferences

Metacharacters `\1` through `\9` are interpreted as backreferences. `\n` matches previously matched subexpression `n`.

Here are some examples:

| Examples of backreferences |  |
| --- | --- |
| Expression | Result |
| (.)\1+ | matches `aaaa` and `cc` |
| (.+)\1+ | also match `abab` and `123123` |
| (['"]?)(\d+)\1 | matches `"13"` (in double quotes), or `'4'` (in single quotes) or `77` (without quotes) etc |

## 6. Assertions (lookahead and lookbehind assertions)

Positive lookahead assertion: `foo(?=bar)` matches `foo` only before `bar`, and `bar` is excluded from the match.

Negative lookahead assertion: `foo(?!bar)` matches `foo` only if it’s not followed by `bar`.

Positive lookbehind assertion: `(?<=foo)bar` matches `bar` only after `foo`, and `foo` is excluded from the match.

Negative lookbehind assertion: `(?<!foo)bar` matches `bar` only if it’s not prefixed with `foo`.

Limitations:

- Brackets for lookahead must be at the very ending of expression, and brackets for lookbehind must be at the very beginning. So assertions between choices `|`, or inside groups, are not supported.
- For lookbehind `(?<!foo)bar`, regular expression `foo` must be of fixed length, ie contains only operations of fixed length matches. Quantifiers are not allowed, except braces with the repeated numbers `{n}` or `{n,n}`. Char-classes are allowed here, dot is allowed, `\b` and `\B` are allowed. Groups and choices are not allowed.
- For other 3 assertion kinds, expression in brackets can be of any complexity.

## 7. Non-capturing groups

Syntax: `(?:expr)`.

Such groups do not have the "index" and are invisible for backreferences. Non-capturing groups are used when you want to group a subexpression, but you do not want to save it as a matched/captured portion of the string. The use of non-capturing groups allows to speed up the work of a regular expression.

| Non-capturing groups |  |
| --- | --- |
| Expression | Result |
| (https?\|ftp)://([^/\r\n]+) | in `https://doublecmd.sourceforge.io` matches `https` and `doublecmd.sourceforge.io` |
| (?:https?\|ftp)://([^/\r\n]+) | in `https://doublecmd.sourceforge.io` matches only `doublecmd.sourceforge.io` |

## 8. Atomic groups

Syntax: `(?>expr|expr|...)`.

Atomic groups are special case of non-capturing groups: this grouping disables backtracking for a parenthesized group if part of the pattern has already been found. Atomic group works faster, useful when optimizing groups with many different expressions.

For example, `a(bc|b)c` matches `abcc` and `abc`, `a(?>bc|b)c` matches `abcc` but not `abc` because the engine is forbidden from backtracking and try with setting the group as `b`.

## 9. Unicode categories

Unicode standard has names for character categories. These are 2-letter strings. For example `Lu` is uppercase letters, `Ll` is lowercase letters. And 1-letter bigger category `L` is all letters.

| Unicode categories |  |
| --- | --- |
| Category | Description |
| L | Letter |
| Lu | Uppercase Letter |
| Ll | Lowercase Letter |
| Lt | Titlecase Letter |
| Lm | Modifier Letter |
| Lo | Other Letter |
|  |  |
| M | Mark |
| Mn | Non-Spacing Mark |
| Mc | Spacing Combining Mark |
| Me | Enclosing Mark |
|  |  |
| N | Number |
| Nd | Decimal Digit Number |
| Nl | Letter Number |
| No | Other Number |
|  |  |
| P | Punctuation |
| Pc | Connector Punctuation |
| Pd | Dash Punctuation |
| Ps | Open Punctuation |
| Pe | Close Punctuation |
| Pi | Initial Punctuation |
| Pf | Final Punctuation |
| Po | Other Punctuation |
|  |  |
| S | Symbol |
| Sm | Math Symbol |
| Sc | Currency Symbol |
| Sk | Modifier Symbol |
| So | Other Symbol |
|  |  |
| Z | Separator |
| Zs | Space Separator |
| Zl | Line Separator |
| Zp | Paragraph Separator |
|  |  |
| C | Other |
| Cc | Control |
| Cf | Format |
| Cs | Surrogate |
| Co | Private Use |
| Cn | Unassigned |

Meta-character `\p` denotes one Unicode char of specified category. Syntaxes: `\pL` and `\p{L}` for 1-letter name, `\p{Lu}` for 2-letter names.

Meta-character `\P` is inverted, it denotes one Unicode char not in the specified category.

These meta-characters are supported withing character classes too.

## 10. Modifiers

Syntax for one modifier: `(?i)` to turn on, and `(?-i)` to turn off. Many modifiers are allowed like this: `(?msgxr-imsgxr)`.

Modifiers are for changing behaviour of regular expressions. Modifier affects only that part of regular expression that follows `(?imsgxr-imsgxr)` operator.

Any of these modifiers may be embedded within the regular expression itself. If modifier is inlined into subexpression, then it effects only into this subexpression.

- `i`
  Do case-insensitive pattern matching (using installed in your system locale settings). Disabled by default.
- `m`
  Treat string as multiple lines. That is, change `^` and `$` from matching at only the very start or end of the string to the start or end of any line anywhere within the string, see also [[Regular Expressions#5.1. Metacharacters - line separators|Line separators]]. Disabled by default.
- `s`
  Treat string as single line. That is, change `.` to match any character whatsoever, even a line separator (see also [[Regular Expressions#5.1. Metacharacters - line separators|Line separators]]), which it normally would not match. Enabled by default.
- `g`
  Non standard modifier. Switching it Off you'll switch all following operators into non-greedy mode (by default this modifier is On). So, if modifier `g` is Off then `+` works as `+?`, `*` as `*?` and so on.
- `x`
  Extend your pattern's legibility by permitting whitespace and comments (see explanation below). Disabled by default.
- `r`
  Non-standard modifier. If is set then range `а-я` additional include Russian letter `ё`, `А-Я` additional include `Ё`, and `а-Я` include all Russian alphabet. Enabled by default.
- `#`
  `(?#text)`: A comment, the `text` is ignored. Note that TRegExpr closes the comment as soon as it sees a `)`, so there is no way to put a literal `)` in the comment.

Here are some examples:

| Examples of Perl extensions |  |
| --- | --- |
| Expression | Result |
| (?i)Saint-Petersburg | matches `Saint-petersburg` and `Saint-Petersburg` |
| (?i)Saint-(?-i)Petersburg | matches `Saint-Petersburg` but not `Saint-petersburg` |
| (?i)(Saint-)?Petersburg | matches `Saint-petersburg` and `saint-petersburg` |
| ((?i)Saint-)?Petersburg | matches `saint-Petersburg` but not `saint-petersburg` |

The modifier `x` itself needs a little more explanation.

It tells to ignore whitespace that is neither backslashed nor within a character class.

You can use this to break up your regular expression into (slightly) more readable parts.

The `#` character is also treated as a metacharacter introducing a comment, for example:

```
(
  (abc) # comment 1
    |   # You can use spaces to format r.e. - TRegExpr ignores it
  (efg) # comment 2
)
```

This also means that if you want real whitespace or `#` characters in the pattern (outside a character class, where they are unaffected by `x`), that you'll either have to escape them or encode them using octal or hex escapes.

Taken together, these features go a long way towards making regular expressions text more readable.

---

[[Indice|← Index]]
