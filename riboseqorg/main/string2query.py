#!/usr/bin/env python
"""Convert string to tree which could be used for queries."""
from django.db.models import Q
from typing import List, Tuple, Dict, Any
from functools import reduce
from operator import or_
from django.db.models import QuerySet
from rest_framework.exceptions import ValidationError
from rest_framework import status


def is_balanced(expression: str) -> bool:
    """
    Check if a given expression has balanced parentheses and square brackets.

    The function takes a string as input and checks whether the parentheses ('()') 
    and square brackets ('[]') are balanced in the expression.

    Args:
        expression (str): The input expression to check for balanced parentheses and square brackets.

    Returns:
        bool: True if the expression is balanced, False otherwise.

    Examples:
        >>> is_balanced("A+(B*C)+(D*E)")
        True

        >>> is_balanced("A+(B*C+(D*E)")
        False
    """
    open_list = ["[", "("]
    close_list = ["]", ")"]
    stack = []

    for i, char in enumerate(expression):
        if char in open_list:
            if i != 0 and expression[i - 1] != "\\":
                stack.append(char)
                continue
            stack.append(char)
        elif char in close_list:
            if i != 0 and expression[i - 1] != "\\":
                pos = close_list.index(char)
                if (len(stack) > 0) and (open_list[pos] == stack[len(stack) - 1]):
                    stack.pop()
                else:
                    return False
    return not stack


def extract_value_field(input_string: str) -> tuple:
    """
    Extracts the value and field from a given input string.

    The function takes a string as input and extracts the value and field.
    The field is enclosed in square brackets, e.g., "Malawi[country]".

    Args:
        input_string (str): The input string containing a value and an optional field.

    Returns:
        tuple: A tuple containing the extracted value and field. If field is not provided, "all" is used.
               If the value is not present, returns None.

    Examples:
        >>> extract_value_field("Malawi[country]")
        ("Malawi", "country")

        >>> extract_value_field("Malawi")
        ("Malawi", "all")
    """
    value, field = "", ""
    temp_field = False

    for char in input_string:
        if char == "[":
            temp_field = True
            continue
        if temp_field:
            if char == "]":
                continue
            field += char
        else:
            value += char

    if not value.strip():
        return None, None

    if not field.strip():
        field = "all"

    return value.strip(), field.strip()


class Stack:
    """A simple stack implementation."""

    def __init__(self):
        """Initialize an empty stack."""
        self.items = []

    def push(self, value):
        """Push a value onto the stack."""
        self.items.append(value)

    def peek(self):
        """Return the top value of the stack without removing it."""
        return self.items[-1] if self.items else 0

    def pop(self):
        """Remove and return the top value of the stack."""
        return self.items.pop() if self.items else 0

    def length(self):
        """Return the length of the stack."""
        return len(self.items)

    def is_empty(self):
        """Check if the stack is empty."""
        return not bool(self.items)

    def display(self):
        """Display the values of the stack."""
        if not self.is_empty():
            temp_stack = Stack()
            while not self.is_empty():
                last_val = self.peek()
                temp_stack.push(last_val)
                self.pop()
            while not temp_stack.is_empty():
                last_val = temp_stack.peek()
                self.push(last_val)
                temp_stack.pop()

    def not_greater(self, operand):
        """Checks whether the role of operand is greater."""
        # NOTE: For the task in this program order is not important as the are
        # separated by ()
        precedence = {"+": 1, "-": 1, "*": 2, "/": 2, "%": 2, "^": 3}
        if self.peek() == "(":
            return False
        operand_a = precedence[operand]
        operand_b = precedence[self.peek()]
        return bool(operand_a <= operand_b)

    def is_less_or_equal_precedence(self, operand):
        """Check if the precedence of the operand is less than or equal to the top of the stack."""
        precedence = {"+": 1, "-": 1, "*": 2, "/": 2, "%": 2, "^": 3}
        return not self.is_empty() and self.peek() != "(" and precedence[operand] <= precedence[self.peek()]

    def infix_to_postfix(self, exp):
        """
        Convert infix expression to postfix expression.

        Args:
            exp (str): Infix expression.

        Returns:
            str: Postfix expression.

        Raises:
            ValueError: If there is an issue with the parentheses in the expression.
        """
        output = ""

        for character in exp:

            if character.isalpha():  # check if operand add to output
                output = output + character

            # If the character is an '(', push it to stack
            elif character == "(":
                self.push(character)

            elif character == ")":  # if ')' pop till '('
                while not self.is_empty() and self.peek() != "(":
                    output += self.pop()
                    # output = output + last
                if not self.is_empty() and self.peek() != "(":
                    return -1
                _ = self.pop()
            else:
                while not self.is_empty() and self.not_greater(character):
                    output += self.pop()
                self.push(character)

        # pop all the operator from the stack
        while not self.is_empty():
            output += self.pop()
            # output = output + last
        return output


def str_to_eq(input_string):
    """
    Converts a given string to a mathematical equation and operand dictionary.

    Args:
        input_string (str): Input string with logical operators and operands.

    Returns:
        tuple: A tuple containing the mathematical equation and operand dictionary.

    Example:
        >>> str_to_eq("~amplicons | (South Africa[country] & cancer[disease]) | (Malawi[country] & Illumina[platform])")
        ('A+(B*C)+(D*E)', {'A': ('~amplicons', 'all'), 'B': ('South Africa', 'country'),
                           'C': ('cancer', 'disease'), 'D': ('Malawi', 'country'),
                           'E': ('Illumina', 'platform')})
    """
    init_chr = 65  # "A"
    qvalue = ""
    value_dict = {}
    my_equation = ""
    for character in input_string:
        if character in "(&|)":
            if qvalue:
                vtype = extract_value_field(qvalue)
                if vtype[0]:
                    my_equation += chr(init_chr)
                    value_dict[chr(init_chr)] = vtype
                    init_chr += 1

                qvalue = ""
            if character == "&":
                my_equation += "*"
            elif character == "|":
                my_equation += "+"
            else:
                my_equation += character
        else:
            qvalue += character

    if qvalue:
        my_equation += chr(init_chr)
        value_dict[chr(init_chr)] = extract_value_field(qvalue)

    return my_equation, value_dict


def query_Q(model, query: Tuple, exclude: List) -> Q:
    """
    Build a Q object based on the query and excluded fields.

    Args:
        - model: The model type.
        - query (Tuple[str, str]): The search query as a tuple (value, field_name).
        - exclude (List[str]): The list of fields to exclude.

    Returns:
        - (Q): Django Q object.
    """
    value, field_name = query
    is_negated = field_name.startswith("~")
    field_name = field_name[1:] if is_negated else field_name
    field_names = [field.name for field in model._meta.get_fields() if field.name not in exclude]
    if field_name in field_names:
        q_lookup = f'{field_name}__icontains'
        return ~Q(**{q_lookup: value}) if is_negated else Q(**{q_lookup: value})

    # If field name is not in model's fields, build a more general query
    general_conditions = [Q(**{f'{field}__icontains': value}) for field in field_names if field not in exclude]
    return reduce(or_, general_conditions, Q())


def eq2query(postfix: list, diction: Dict, model) -> QuerySet:
    """
    Convert postfix to Query.

    Args:
        - postfix (str): Postfix expression.
        - diction (Dict[str, Tuple[str, str]]): Dictionary mapping variables to (value, field_name)tuples.
        - model (Any): The model type.

    Returns:
        - QuerySet: QuerySet based on the postfix expression.
    """
    to_calculate = []
    to_operate = []
    while postfix:
        current = postfix.pop()
        if current in "+*":
            to_operate.append(current)
        else:
            if None in diction[current]:
                continue
            to_calculate.append(query_Q(model, diction[current], exclude=["id", "verified", "trips_id", "gwips_id", "ribocrypt_id", "FASTA_file"]))
            if len(to_calculate) >= 2:
                first = to_calculate.pop()
                second = to_calculate.pop()
                operator = to_operate.pop()
                if operator == "+":
                    query = first & second
                if operator == "*":
                    query = first | second
                to_calculate.append(query)
    return to_calculate[0]


def query2sqlquery(user_query: str, model: Any) -> str:
    """
    Convert a user query to an SQL query.char in "&|"

    Args:
        - user_query (str): The user-provided query string.
        - model (YourModelType): The model used for processing the query.

    Returns:
        str: The generated SQL query.

    Raises:
        ValidationError: If the query has mismatching brackets.
    """
    user_query = user_query.replace(
        " OR ", " | "
        ).replace(
            " AND ", " & "
            ).strip('"')

    infix_equation, diction = str_to_eq(user_query)

    if not is_balanced(infix_equation):
        error_message = f"Invalid query (mismatching brackets): '{user_query}'"
        raise ValidationError(
            detail={'ERROR': error_message},
            code=status.HTTP_400_BAD_REQUEST
        )

    postfix_equation = list(Stack().infix_to_postfix(infix_equation))
    print(postfix_equation)
    sql_query = eq2query(postfix_equation, diction, model)

    return sql_query
