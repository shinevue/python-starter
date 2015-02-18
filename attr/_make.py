# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import copy
import hashlib
import linecache

from ._compat import exec_, iteritems


class _Nothing(object):
    """
    Sentinel class to indicate the lack of a value when ``None`` is ambiguous.

    All instances of `_Nothing` are equal.
    """
    def __copy__(self):
        return self

    def __deepcopy__(self, _):
        return self

    def __eq__(self, other):
        return self.__class__ == _Nothing

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "NOTHING"


NOTHING = _Nothing()
"""
Sentinel to indicate the lack of a value when ``None`` is ambiguous.
"""


def attr(default=NOTHING, validator=None, no_repr=False, no_cmp=False,
         no_hash=False, no_init=False):
    """
    Create a new attribute on a class.

    .. warning::

        Does *not* do anything unless the class is also decorated with
        :func:`attr.s`!

    :param default: Value that is used if an ``attrs``-generated
        ``__init__`` is used and no value is passed while instantiating.  If
        the value an instance of :class:`Factory`, it callable will be use to
        construct a new value (useful for mutable datatypes like lists or
        dicts).
    :type default: Any value.

    :param validator: :func:`callable` that is called by ``attrs``-generated
        ``__init__`` methods after the instance has been initialized.  They
        receive the initialized instance, the :class:`Attribute`, and the
        passed value.

        The return value is *not* inspected so the validator has to throw an
        exception itself.
    :type validator: callable

    :param no_repr: Exclude this attribute when generating a ``__repr__``.
    :type no_repr: bool

    :param no_cmp: Exclude this attribute when generating comparison methods
        (``__eq__`` et al).
    :type no_cmp: bool

    :param no_hash: Exclude this attribute when generating a ``__hash__``.
    :type no_hash: bool

    :param no_init: Exclude this attribute when generating a ``__init__``.
    :type no_init: bool
    """
    return _CountingAttr(
        default=default,
        validator=validator,
        no_repr=no_repr,
        no_cmp=no_cmp,
        no_hash=no_hash,
        no_init=no_init,
    )


def _transform_attrs(cl, these):
    """
    Transforms all `_CountingAttr`s on a class into `Attribute`s and saves the
    list in `__attrs_attrs__`.

    If *these* is passed, use that and don't look for them on the class.
    """
    super_cls = []
    for c in reversed(cl.__mro__[1:-1]):
        sub_attrs = getattr(c, "__attrs_attrs__", None)
        if sub_attrs is not None:
            super_cls.extend(sub_attrs)
    if these is None:
        ca_list = [(name, attr)
                   for name, attr
                   in cl.__dict__.items()
                   if isinstance(attr, _CountingAttr)]
    else:
        ca_list = [(name, ca)
                   for name, ca
                   in iteritems(these)]

    cl.__attrs_attrs__ = super_cls + [
        Attribute.from_counting_attr(name=attr_name, ca=ca)
        for attr_name, ca
        in sorted(ca_list, key=lambda e: e[1].counter)
    ]

    had_default = False
    for a in cl.__attrs_attrs__:
        if these is None:
            setattr(cl, a.name, a)
        if had_default is True and a.default is NOTHING:
            raise ValueError(
                "No mandatory attributes allowed after an attribute with a "
                "default value or factory.  Attribute in question: {a!r}"
                .format(a=a)
            )
        elif had_default is False and a.default is not NOTHING:
            had_default = True


def attributes(maybe_cl=None, these=None,
               no_repr=False, no_cmp=False, no_hash=False, no_init=False):
    """
    A class decorator that adds `dunder
    <https://wiki.python.org/moin/DunderAlias>`_\ -methods according to the
    specified attributes using :func:`attr.ib` or the *these* argument.

    :param these: A dictionary of name to :func:`attr.ib` mappings.  This is
        useful to avoid the definition of your attributes within the class body
        because you can't (e.g. if you want to add ``__repr__`` methods to
        Django models) or don't want to (e.g. if you want to use
        :class:`properties <property>`).

        If *these* is not `None`, the class body is *ignored*.
    :type these: class:`dict` of :class:`str` to :func:`attr.ib`

    :param no_repr: Don't create a ``__repr__`` method with a human readable
        represantation of ``attrs`` attributes..
    :type no_repr: bool

    :param no_cmp: Don't create ``__eq__``, ``__ne__``, ``__lt__``, ``__le__``,
        ``__gt__``, and ``__ge__`` methods that compare the class as if it were
        a tuple of its ``attrs`` attributes.  But the attributes are *only*
        compared, if the type of both classes is *identical*!
    :type no_cmp: bool

    :param no_hash: Don't add a ``__hash__`` method that returns the
        :func:`hash` of a tuple of all ``attrs`` attribute values.
    :type no_hash: bool

    :param no_init: Don't add a ``__init__`` method that initialiazes the
        ``attrs`` attributes.  Leading underscores are stripped for the
        argument name.

    :type no_init: bool
    """
    def wrap(cl):
        if getattr(cl, "__class__", None) is None:
            raise TypeError("attrs only works with new-style classes.")
        _transform_attrs(cl, these)
        if not no_repr:
            cl = _add_repr(cl)
        if not no_cmp:
            cl = _add_cmp(cl)
        if not no_hash:
            cl = _add_hash(cl)
        if not no_init:
            cl = _add_init(cl)
        return cl

    # attrs_or class type depends on the usage of the decorator.  It's a class
    # if it's used as `@attributes` but ``None`` if used # as `@attributes()`.
    if maybe_cl is None:
        return wrap
    else:
        return wrap(maybe_cl)


def _attrs_to_tuple(obj, attrs):
    """
    Create a tuple of all values of *obj*'s *attrs*.
    """
    return tuple(getattr(obj, a.name) for a in attrs)


def _add_hash(cl, attrs=None):
    if attrs is None:
        attrs = [a for a in cl.__attrs_attrs__ if not a.no_hash]

    def hash_(self):
        """
        Automatically created by attrs.
        """
        return hash(_attrs_to_tuple(self, attrs))

    cl.__hash__ = hash_
    return cl


def _add_cmp(cl, attrs=None):
    if attrs is None:
        attrs = [a for a in cl.__attrs_attrs__ if not a.no_cmp]

    def attrs_to_tuple(obj):
        """
        Save us some typing.
        """
        return _attrs_to_tuple(obj, attrs)

    def eq(self, other):
        """
        Automatically created by attrs.
        """
        if other.__class__ is self.__class__:
            return attrs_to_tuple(self) == attrs_to_tuple(other)
        else:
            return NotImplemented

    def ne(self, other):
        """
        Automatically created by attrs.
        """
        result = eq(self, other)
        if result is NotImplemented:
            return NotImplemented
        else:
            return not result

    def lt(self, other):
        """
        Automatically created by attrs.
        """
        if isinstance(other, self.__class__):
            return attrs_to_tuple(self) < attrs_to_tuple(other)
        else:
            return NotImplemented

    def le(self, other):
        """
        Automatically created by attrs.
        """
        if isinstance(other, self.__class__):
            return attrs_to_tuple(self) <= attrs_to_tuple(other)
        else:
            return NotImplemented

    def gt(self, other):
        """
        Automatically created by attrs.
        """
        if isinstance(other, self.__class__):
            return attrs_to_tuple(self) > attrs_to_tuple(other)
        else:
            return NotImplemented

    def ge(self, other):
        """
        Automatically created by attrs.
        """
        if isinstance(other, self.__class__):
            return attrs_to_tuple(self) >= attrs_to_tuple(other)
        else:
            return NotImplemented

    cl.__eq__ = eq
    cl.__ne__ = ne
    cl.__lt__ = lt
    cl.__le__ = le
    cl.__gt__ = gt
    cl.__ge__ = ge

    return cl


def _add_repr(cl, attrs=None):
    if attrs is None:
        attrs = [a for a in cl.__attrs_attrs__ if not a.no_repr]

    def repr_(self):
        """
        Automatically created by attrs.
        """
        return "{0}({1})".format(
            self.__class__.__name__,
            ", ".join(a.name + "=" + repr(getattr(self, a.name))
                      for a in attrs)
        )
    cl.__repr__ = repr_
    return cl


def _add_init(cl):
    attrs = [a for a in cl.__attrs_attrs__ if not a.no_init]

    # We cache the generated init methods for the same kinds of attributes.
    sha1 = hashlib.sha1()
    sha1.update(repr(attrs).encode("utf-8"))
    unique_filename = "<attrs generated init {0}>".format(
        sha1.hexdigest()
    )

    script = _attrs_to_script(attrs)
    locs = {}
    bytecode = compile(script, unique_filename, "exec")
    attr_dict = dict((a.name, a) for a in attrs)
    exec_(bytecode, {"NOTHING": NOTHING,
                     "attr_dict": attr_dict,
                     "validate": validate}, locs)
    init = locs["__init__"]

    # In order of debuggers like PDB being able to step through the code,
    # we add a fake linecache entry.
    linecache.cache[unique_filename] = (
        len(script),
        None,
        script.splitlines(True),
        unique_filename
    )
    cl.__init__ = init
    return cl


def fields(cl):
    """
    Returns the list of ``attrs`` attributes for a class.

    :param cl: Class to introspect.
    :type cl: type

    :raise TypeError: If *cl* is not a class.
    :raise ValueError: If *cl* is not an ``attrs`` class.

    :rtype: :class:`list` of :class:`attr.Attribute`
    """
    if not isinstance(cl, type):
        raise TypeError("Passed object must be a class.")
    attrs = getattr(cl, "__attrs_attrs__", None)
    if attrs is None:
        raise ValueError("{cl!r} is not an attrs-decorated class.".format(
            cl=cl
        ))
    return copy.deepcopy(attrs)


def validate(inst):
    """
    Validate all attributes on *inst* that have a validator.

    Leaves all exceptions through.

    :param inst: Instance of a class with ``attrs`` attributes.
    """
    for a in fields(inst.__class__):
        if a.validator is not None:
            a.validator(inst, a, getattr(inst, a.name))


def _attrs_to_script(attrs):
    """
    Return a valid Python script of an initializer for *attrs*.
    """
    lines = []
    args = []
    has_validator = False
    for a in attrs:
        if a.validator is not None:
            has_validator = True
        attr_name = a.name
        arg_name = a.name.lstrip("_")
        if a.default is not NOTHING and not isinstance(a.default, Factory):
            args.append(
                "{arg_name}=attr_dict['{attr_name}'].default".format(
                    arg_name=arg_name,
                    attr_name=attr_name,
                )
            )
            lines.append("self.{attr_name} = {arg_name}".format(
                arg_name=arg_name,
                attr_name=attr_name,
            ))
        elif a.default is not NOTHING and isinstance(a.default, Factory):
            args.append("{arg_name}=NOTHING".format(arg_name=arg_name))
            lines.extend("""\
if {arg_name} is not NOTHING:
    self.{attr_name} = {arg_name}
else:
    self.{attr_name} = attr_dict["{attr_name}"].default.factory()"""
                         .format(attr_name=attr_name,
                                 arg_name=arg_name)
                         .split("\n"))
        else:
            args.append(arg_name)
            lines.append("self.{attr_name} = {arg_name}".format(
                attr_name=attr_name,
                arg_name=arg_name,
            ))

    if has_validator:
        lines.append("validate(self)")

    return """\
def __init__(self, {args}):
    '''
    Attribute initializer automatically created by attrs.
    '''
    {setters}
""".format(
        args=", ".join(args),
        setters="\n    ".join(lines),
    )


class Attribute(object):
    """
    *Read-only* representation of an attribute.

    :attribute name: The name of the attribute.

    Plus *all* arguments of :func:`attr.ib`.
    """
    _attributes = [
        "name", "default", "validator", "no_repr", "no_cmp", "no_hash",
        "no_init",
    ]  # we can't use ``attrs`` so we have to cheat a little.

    def __init__(self, **kw):
        if len(kw) > len(Attribute._attributes):
            raise TypeError("Too many arguments.")
        try:
            for a in Attribute._attributes:
                setattr(self, a, kw[a])
        except KeyError:
            raise TypeError("Missing argument '{arg}'.".format(arg=a))

    @classmethod
    def from_counting_attr(cl, name, ca):
        return cl(name=name,
                  **dict((k, getattr(ca, k))
                         for k
                         in Attribute._attributes
                         if k != "name"))


_a = [Attribute(name=name, default=NOTHING, validator=None, no_repr=False,
                no_cmp=False, no_hash=False, no_init=False)
      for name in Attribute._attributes]
Attribute = _add_hash(
    _add_cmp(_add_repr(Attribute, attrs=_a), attrs=_a), attrs=_a
)


class _CountingAttr(object):
    __attrs_attrs__ = [
        Attribute(name=name, default=NOTHING, validator=None, no_repr=False,
                  no_cmp=False, no_hash=False, no_init=False)
        for name
        in ("counter", "default", "no_repr", "no_cmp", "no_hash", "no_init",)
    ]
    counter = 0

    def __init__(self, default, validator, no_repr, no_cmp, no_hash, no_init):
        _CountingAttr.counter += 1
        self.counter = _CountingAttr.counter
        self.default = default
        self.validator = validator
        self.no_repr = no_repr
        self.no_cmp = no_cmp
        self.no_hash = no_hash
        self.no_init = no_init


_CountingAttr = _add_cmp(_add_repr(_CountingAttr))


@attributes
class Factory(object):
    """
    Stores a factory callable.

    If passed as the default value to :func:`attr.ib`, the factory is used to
    generate a new value.
    """
    factory = attr()


def make_class(name, attrs, **attributes_arguments):
    """
    A quick way to create a new class called *name* with *attrs*.

    :param name: The name for the new class.
    :type name: str

    :param attrs: A list of names or a dictionary of mappings of names to
        attributes.
    :type attrs: :class:`list` or :class:`dict`

    :param attributes_arguments: Passed unmodified to :func:`attr.s`.

    :return: A new class with *attrs*.
    :rtype: type
    """
    if isinstance(attrs, dict):
        cl_dict = attrs
    elif isinstance(attrs, (list, tuple)):
        cl_dict = dict((a, attr()) for a in attrs)
    else:
        raise TypeError("attrs argument must be a dict or a list.")

    return attributes(**attributes_arguments)(type(name, (object,), cl_dict))
