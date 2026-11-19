# Narration for the "Python Numbers" tutorial video.
# Spoken forms are written out on purpose (e.g. "ten, floor-divided by three") so the voice reads code naturally.
# Each lesson has two parts: "concept" (shown with the explanation slide) and "walk" (shown with the code + output slide).

TITLE = "Python Numbers: A Complete Tutorial"
VOICE_DEFAULT = "en-US-AndrewNeural"

INTRO = [
 "Good day to everyone. Hi, my name is Glenn, and I will be your guide for today's Python tutorial, which is Python numbers.",
 "Numbers are the foundation of almost everything you will build. Calculators, games, and shopping carts use them. So do banking and accounting software, scientific simulations, machine learning, and data analysis. If you can work confidently with numbers, you can solve a very wide range of problems.",
 "In this lesson, we will cover three numeric types: integers, floating-point numbers, and complex numbers. Then we will study the arithmetic operators, the math module, random numbers, exact arithmetic with Decimal and Fraction, and finally how to format numbers for display.",
 "Each topic has two parts. First, I will explain the concept. Then we will walk through a real program, line by line, and look at its actual output. This tutorial is meant for beginners, and it is also a good refresher for experienced programmers.",
 "I recommend that you pause the video often, open the interactive lesson on Poetic Bytes, run every example yourself, and change the values to see what happens. That is the fastest way to learn. Now, let's begin.",
]

LESSONS = [
 {
  "id": "1.1", "title": "Creating Integers",
  "concept": "An integer is a whole number with no decimal point. You can create one by writing the number directly, or by converting a value with the int function. The int function can even read text, and it accepts a base, which lets you interpret a string as a binary number.",
  "walk": "On the first two lines, we assign forty-two and negative seventeen. Python infers the type for us. Next, int of the string one hundred converts text into the number one hundred. Then, int of the string one, zero, one, zero, with a base of two, reads that text as binary, and the result is ten. Finally, the print statements use the type function to confirm each value. Notice that all four results report the class int.",
 },
 {
  "id": "1.2", "title": "Arbitrary Precision",
  "concept": "Unlike many languages, Python integers have no fixed size. They grow as large as your computer's memory allows, so you never have to worry about integer overflow.",
  "walk": "We start with ten raised to the power of one hundred, which is a one followed by one hundred zeros. Converting it to a string and taking its length shows that it has one hundred and one digits. Then we multiply the number by itself, producing ten to the power of two hundred. Python handles this without any special code, and the result has two hundred and one digits.",
 },
 {
  "id": "2.1", "title": "Creating Floats",
  "concept": "Floating-point numbers represent real numbers, meaning numbers with a fractional part. You can write them with a decimal point, in scientific notation, or by converting with the float function.",
  "walk": "Here, pi is three point one, four, one, five, nine, and neg is negative two point five. The variable e_charge uses scientific notation: one point six, e, negative nineteen, which means one point six times ten to the negative nineteenth power. Finally, float of the string three point one four converts text into a float. Each print statement confirms that the type is float.",
 },
 {
  "id": "2.2", "title": "Special Float Values",
  "concept": "Floats also include three special values: positive infinity, negative infinity, and N-a-N, which stands for not a number. You create them with the float function, and you test for them with the math module.",
  "walk": "We import math, then create inf, negative inf, and nan from strings. The functions math dot isinf and math dot isnan return True for each of them. Now look at the last two lines. Infinity plus five is still infinity. But infinity divided by infinity is undefined, so Python returns nan. A key rule to remember: you should never compare values to nan with the equals operator. Always use math dot isnan.",
 },
 {
  "id": "3.1", "title": "Creating Complex Numbers",
  "concept": "Python has built-in support for complex numbers. A complex number has a real part and an imaginary part, and Python uses the letter j for the imaginary unit.",
  "walk": "We create z as three plus four j. We can also build one with the complex function, as in z two, which is two minus one j. The attributes dot real and dot imag give the two parts, and Python reports them as floats. The conjugate method flips the sign of the imaginary part, giving three minus four j. At the bottom, adding z and z two gives five plus three j, and multiplying them gives ten plus five j. Python follows the usual rules of complex arithmetic for you.",
 },
 {
  "id": "3.2", "title": "Complex Number Functions",
  "concept": "For deeper work with complex numbers, import the cmath module. It provides the phase, the polar form, and conversion back to rectangular coordinates. The built-in abs function returns the magnitude.",
  "walk": "With z equal to three plus four j, abs of z returns five, the length of the vector from the origin. The phase function returns the angle, about zero point nine three radians. The polar function returns both values together as a pair. We then unpack them into r and theta, and rect converts them back. Look closely at the result. It is almost three plus four j, but with tiny rounding differences in the last digits. That is normal floating-point behavior, and we will return to it shortly.",
 },
 {
  "id": "4.1", "title": "Basic Operators",
  "concept": "Python provides seven arithmetic operators: addition, subtraction, multiplication, division, floor division, modulo, and exponentiation. Two of them are worth special attention. Regular division always returns a float, while floor division returns a whole number.",
  "walk": "We set a to ten and b to three. Addition gives thirteen, subtraction gives seven, and multiplication gives thirty. Division gives three point three, three, three, and so on, a float. Floor division, written with two slashes, discards the fraction and gives three. Modulo, the percent sign, gives the remainder, which is one. And the double asterisk raises ten to the power of three, giving one thousand.",
 },
 {
  "id": "4.2", "title": "Augmented Assignment",
  "concept": "Augmented assignment combines an operation with assignment. Instead of writing x equals x plus three, you can write x plus-equals three. It is shorter, clearer, and very common in loops.",
  "walk": "We begin with x equal to ten. Plus-equals three makes it thirteen. Minus-equals five brings it to eight. Times-equals two gives sixteen. Floor-divide-equals four gives four. And finally, power-equals two squares it, returning to sixteen. Follow the value line by line, and you can see exactly how each operator updates the same variable.",
 },
 {
  "id": "5.1", "title": "Common math Functions",
  "concept": "The math module extends Python with the functions you would find on a scientific calculator: square roots, trigonometry, logarithms, factorials, and combinations. Always begin by importing the module.",
  "walk": "After the import, math dot sqrt of twenty-five returns five point zero. The constant math dot pi gives pi to fifteen decimal places. The sine of pi over two is one, as expected. math dot log of one hundred, with base ten, returns two, because ten squared is one hundred. math dot log two of eight is three. Then math dot factorial of five is one hundred and twenty, and math dot comb of five and two gives ten, the number of ways to choose two items from five.",
 },
 {
  "id": "5.2", "title": "Constants and Special Functions",
  "concept": "The math module also offers useful constants, such as e and tau, along with ceiling, floor, the greatest common divisor, and a safe way to compare floats.",
  "walk": "math dot e is Euler's number, and math dot tau equals two times pi, one full turn of a circle. The ceil function rounds three point one four up to four, while floor rounds it down to three. The gcd function finds that the greatest common divisor of forty-eight and eighteen is six. And the last line is important. Adding zero point one and zero point two does not exactly equal zero point three in floating point, but math dot isclose compares them with a tolerance and returns True. Use isclose whenever you compare floats.",
 },
 {
  "id": "6.1", "title": "Basic Random Functions",
  "concept": "The random module generates pseudo-random numbers for games, simulations, and testing. It can produce floats and integers, pick from a list, shuffle a list, and draw a sample without repeats.",
  "walk": "random dot random returns a float between zero and one. random dot randint of one and ten returns an integer, and both endpoints are possible. random dot choice picks one item from the colors list. random dot shuffle reorders a list in place, which is why we do not assign its result. And random dot sample draws five different numbers from the range zero to ninety-nine. Because the values are random, your output will differ from what you see here, and that is exactly what we want.",
 },
 {
  "id": "6.2", "title": "Seeding for Reproducibility",
  "concept": "Sometimes you need random numbers that are repeatable, for example when you are debugging, or when you want research results that others can reproduce. You do that by setting a seed.",
  "walk": "We call random dot seed with forty-two, and then draw three random integers between one and one hundred. Next, we set the same seed again and draw another three. Compare the two sequences. Both are eighty-two, fifteen, and four. The same seed always produces the same sequence. So if a test fails once, you can reproduce it exactly.",
 },
 {
  "id": "7.1", "title": "Decimal: Exact Decimal Arithmetic",
  "concept": "Floats are stored in binary, so some decimal fractions cannot be represented exactly. For money and other cases where exactness matters, use the Decimal class. Always create decimals from strings, not from floats.",
  "walk": "The first line shows the classic problem. In floating point, zero point one plus zero point two gives zero point three, zero, zero, zero, and a tail of tiny error. With Decimal, created from strings, the answer is exactly zero point three. Next, getcontext dot prec sets the precision to four significant digits, so one divided by three prints as zero point three, three, three, three. Finally, a price of nineteen ninety-nine with an eight percent tax gives twenty-one fifty-nine. Notice that the precision of four is still active, which is why the total is rounded.",
 },
 {
  "id": "7.2", "title": "Fraction: Rational Numbers",
  "concept": "The Fraction class represents rational numbers exactly, as a numerator over a denominator. Results are always reduced to their simplest form.",
  "walk": "We create three-quarters and one-sixth. Adding them gives eleven twelfths, since they share the common denominator of twelve. Multiplying gives one eighth, reduced automatically from three twenty-fourths. Dividing gives nine halves. And at the bottom, Fraction of the string zero point one two five converts a decimal text into exactly one eighth. There is no rounding error anywhere.",
 },
 {
  "id": "8.1", "title": "Formatting Floats",
  "concept": "Formatting controls how a number is displayed, without changing its value. In an f-string, you place a format specifier after a colon. For floats, you can set the decimal places, add thousands separators, show percentages, or use scientific notation.",
  "walk": "The specifier colon dot two f rounds pi to two decimals, giving three point one four. Dot four f gives three point one, four, one, six. Dot two e switches to scientific notation, three point one four e plus zero zero. A comma before the dot adds thousands separators, so one million two hundred thirty-four thousand appears with commas. And dot two percent multiplies by one hundred and adds a percent sign, turning zero point eight, seven, five into eighty-seven point five zero percent.",
 },
 {
  "id": "8.2", "title": "Formatting Integers",
  "concept": "Integers can be displayed in different bases and padded to a fixed width. This is useful for binary, hexadecimal, and for neat, aligned output.",
  "walk": "With n equal to forty-two, the letter d prints decimal. The letter b prints binary, one, zero, one, zero, one, zero. The letter o prints octal, five, two. The letter x prints hexadecimal, two a, and a capital X prints it in uppercase. Then zero five d pads with zeros to a width of five, giving zero, zero, zero, four, two. And five d on its own pads with spaces instead.",
 },
]

OUTRO = [
 "Congratulations. You now understand every numeric type in Python, and the tools to work with them.",
 "Let's recap. Integers are unlimited in size. Floats are fast, but approximate. Complex numbers have real and imaginary parts. The math module covers advanced functions. Random numbers can be reproduced with a seed. Decimal and Fraction give exact results. And format specifiers control how numbers look.",
 "To practice, open the interactive lessons on Poetic Bytes, run every example, and change the values to see what happens. Try small projects too, such as a tip calculator, a dice game, or a unit converter.",
 "Thank you for learning with me. My name is Glenn, and this has been Python numbers. If this tutorial helped you, please like, subscribe, and share it with a friend who is learning Python. I will see you in the next lesson.",
]

# Extra background and professional tips, appended to each lesson's spoken text (edit freely).
EXTRA = {
 "1.1": ("Integers are the type you will use most often: counting items, indexing lists, and looping. Negative numbers work exactly the same way. If you need a different base, remember that the int function accepts bases from two up to thirty-six.",
         "A good habit is to use the type function whenever you are unsure what you are holding. It saves a lot of debugging time."),
 "1.2": ("In languages such as C or Java, an integer has a fixed size, and a calculation that is too large silently wraps around. Python avoids that whole class of bugs. This is why Python is popular for cryptography and for mathematical work with very large numbers.",
         "The only limit is memory, and very large numbers do take longer to calculate. For everyday programs, you will never notice."),
 "2.1": ("Floats follow an international standard called I-E-E-E seven fifty-four, and they use sixty-four bits of storage. They hold about fifteen to seventeen significant digits. Scientific notation is a convenient way to write very large or very small values.",
         "Remember that a float is an approximation. We will see why that matters in a moment, when we study Decimal."),
 "2.2": ("Infinity is useful as a starting value when you search for a minimum or a maximum. Nan usually appears when a calculation has no meaningful answer, such as infinity minus infinity.",
         "Nan has a surprising property: it is not equal to anything, not even to itself. That is exactly why the isnan function exists."),
 "3.1": ("Complex numbers are used in electrical engineering, signal processing, physics, and graphics. Most languages need a library for them, but in Python they are built in. Notice that Python uses j for the imaginary unit, the convention used in engineering, and not the letter i.",
         "Note that you must write the number directly in front of the j, with no space. So three j works, but j on its own would be read as a variable name."),
 "3.2": ("The magnitude is the distance from the origin, the phase is the angle, and together they are called the polar form. Polar form makes rotation and scaling very easy to express.",
         "Use cmath, and not math, whenever your values may be complex. The math module will raise an error if you give it a complex number."),
 "4.1": ("Operator precedence matters. Exponentiation is evaluated first, then multiplication, division, floor division and modulo, and finally addition and subtraction. When in doubt, use parentheses, because they make your intent obvious to the reader.",
         "A common use of modulo is to test whether a number is even: if n modulo two equals zero, it is even. Also note that floor division rounds toward negative infinity, so negative seven floor-divided by two gives negative four, not negative three."),
 "4.2": ("Every arithmetic operator has an augmented form, and the same idea applies to bitwise operators too. They are not just shorter; for some types, they can update a value in place.",
         "Be careful to start with a value that already exists. Writing plus-equals on a variable that was never defined raises a name error."),
 "5.1": ("The math module is written in C, so it is fast and reliable. Angles in trigonometric functions are measured in radians, not degrees. If you have degrees, convert them first with math dot radians.",
         "Also remember that math dot sqrt of a negative number raises an error. For that case, use cmath dot sqrt, which returns a complex result."),
 "5.2": ("Rounding is a common source of confusion. The ceil function always rounds up, floor always rounds down, and the built-in round function rounds to the nearest value, with exact halves going to the nearest even number.",
         "In real programs, never test floats for exact equality. Use isclose, and choose a tolerance that fits your problem."),
 "6.1": ("The random module uses an algorithm called the Mersenne Twister. It is excellent for games, simulations, and testing, but it is not secure. For passwords, tokens, or anything related to security, use the secrets module instead.",
         "There are many more functions, such as uniform for a random float in a range, and choices for picking several items with replacement."),
 "6.2": ("A seed is the starting point of the random sequence. The sequence looks random, but it is completely determined by the seed. That is why we call these numbers pseudo-random.",
         "In automated tests, always set a seed. Then your tests give the same results every time, and failures are easy to reproduce."),
 "7.1": ("The reason for the float problem is that computers store numbers in binary, and a value such as zero point one has an endless binary expansion. This is not a Python bug. Every language that uses standard floats behaves the same way.",
         "For money, many professionals use Decimal, or they store amounts in whole cents as integers. Either way, they avoid floats for currency."),
 "7.2": ("Use Fraction when you need exact ratios, for example in recipes, music theory, or mathematical proofs. Every operation keeps the result exact, and it is always reduced to lowest terms.",
         "You can also convert a float to a nearby simple fraction with the limit denominator method, which is handy for display."),
 "8.1": ("Formatting only changes how a number looks. The stored value is not changed. This is a very important idea: format at the last moment, when you display the result, and keep full precision in your calculations.",
         "You can combine specifiers. For example, a comma, then dot two f, shows a number with thousands separators and two decimals, which is perfect for prices."),
 "8.2": ("The same format mini-language works everywhere: in f-strings, in the format function, and in the format method of strings. Padding with zeros is common for identifiers, dates, and file names.",
         "If you only need a quick conversion, the built-in functions bin, oct, and hex do the same job, and they add a prefix such as zero x."),
}
for _l in LESSONS:
    _c, _w = EXTRA[_l["id"]]
    _l["concept"] = _l["concept"] + " " + _c
    _l["walk"] = _l["walk"] + " " + _w


# Step-by-step cues for the laptop scenes. One entry per spoken sentence of the "walk" text, in order:
#   (first_line, last_line, output_lines_visible)  -> those code lines are typed and highlighted while the sentence is spoken
# Sentences after the last cue show the whole program and its full output (these are the tips).
CUES = {
 "1.1": [(1,2,0),(1,2,0),(3,3,0),(4,4,0),(6,9,4),(6,9,4)],
 "1.2": [(1,1,0),(2,3,2),(5,5,2),(6,7,4)],
 "2.1": [(1,2,0),(3,3,0),(4,4,0),(6,9,4)],
 "2.2": [(1,5,0),(7,9,3),(11,12,3),(11,11,4),(12,12,5)],
 "3.1": [(1,1,0),(2,2,0),(4,6,3),(7,7,4),(9,10,6)],
 "3.2": [(3,6,2),(7,7,3),(8,8,4),(10,11,5)],
 "4.1": [(1,1,0),(3,5,3),(6,6,4),(7,7,5),(8,8,6),(9,9,7)],
 "4.2": [(1,2,1),(4,5,2),(7,8,3),(10,11,4),(13,14,5),(16,17,6)],
 "5.1": [(1,3,1),(4,4,2),(5,5,3),(6,6,4),(7,7,5),(8,9,7)],
 "5.2": [(1,4,2),(5,6,4),(7,7,5),(8,8,5),(8,8,6)],
 "6.1": [(1,3,1),(4,4,2),(6,7,3),(9,11,4),(13,14,5)],
 "6.2": [(1,6,4),(8,11,8)],
 "7.1": [(1,3,1),(3,3,1),(4,4,2),(6,7,3),(9,12,4)],
 "7.2": [(1,4,0),(6,8,3),(9,9,4),(10,10,5),(12,13,6)],
 "8.1": [(1,4,1),(5,5,2),(6,6,3),(8,8,4),(10,11,5)],
 "8.2": [(1,3,1),(4,4,2),(5,5,3),(6,7,5),(9,9,6),(10,10,7)],
}
