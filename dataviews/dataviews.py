import numpy as np
from collections import defaultdict

import param

from ndmapping import NdMapping, map_type
from views import View, Overlay, Annotation, Layout, GridLayout

def find_minmax(lims, olims):
    """
    Takes (a1, a2) and (b1, b2) as input and returns
    (np.min(a1, b1), np.max(a2, b2)).
    """

    limzip = zip(list(lims), list(olims), [np.min, np.max])
    return tuple([float(fn([l, ol])) for l, ol, fn in limzip])



class DataLayer(View):
    """
    General purpose DataLayer for holding data to be plotted along some
    axes. Subclasses can implement specialized containers for data such as
    curves, points, bars or surfaces.
    """

    xlabel = param.String(default='', doc="X-axis label")

    ylabel = param.String(default='', doc="Y-axis label")

    legend_label = param.String(default="", doc="Legend labels")

    def __mul__(self, other):
        if isinstance(other, DataStack):
            items = [(k, self * v) for (k, v) in other.items()]
            return other.clone(items=items)
        elif isinstance(self, DataOverlay):
            if isinstance(other, DataOverlay):
                overlays = self.data + other.data
            else:
                overlays = self.data + [other]
        elif isinstance(other, DataOverlay):
            overlays = [self] + other.data
        elif isinstance(other, DataLayer):
            overlays = [self, other]
        else:
            raise TypeError('Can only create an overlay of DataViews.')

        return DataOverlay(overlays, metadata=self.metadata)



class Curve(DataLayer):
    """
    Curve can contain a list of curves with associated metadata and
    cyclic_range parameter to indicate with what periodicity the curve wraps.
    """

    cyclic_range = param.Number(default=None, allow_None=True)


    def __init__(self, data, **kwargs):
        super(Curve, self).__init__(np.array(data), **kwargs)


    @property
    def xlim(self):
        x_vals = self.data[:, 0]
        return (min(x_vals), self.cyclic_range if self.cyclic_range else float(max(x_vals)))


    @property
    def ylim(self):
        y_vals = self.data[:, 1]
        y_min = min(y_vals)
        y_max = max(y_vals)
        return (float(y_min), float(y_max))


    @property
    def lbrt(self):
        l, r = self.xlim
        b, t = self.ylim
        return float(l), float(b), float(r), float(t)


    def stack(self):
        stack = DataStack(None, dimensions=[self.xlabel],
                          title=self.title+' {dims}', **self.metadata)
        for idx in range(len(self.data)):
            x = self.data[0]
            if x in stack:
                stack[x].data.append(self.data[0:idx])
            else:
                stack[x] = Curve(self.data[0:idx])
        return stack



class Histogram(DataLayer):
    """
    Histogram contains a number of bins, which are defined by the upper
    and lower bounds of their edges and the computed bin values.
    """

    cyclic_range = param.Number(default=None, allow_None=True, doc="""
       Cyclic-range should be set when the bins are sampling a cyclic
       quantity.""")

    def __init__(self, values, edges, **kwargs):
        self.values, self.edges = self._process_data(values, edges)
        super(Histogram, self).__init__((self.values, self.edges), **kwargs)


    def _process_data(self, values, edges):
        """
        Ensure that edges are specified as left and right edges of the
        histogram bins rather than bin centers.
        """
        values = np.array(values)
        edges = np.array(edges, dtype=np.float)
        if len(edges) == len(values):
            widths = list(set(np.diff(edges)))
            if len(widths) == 1:
                width = widths[0]
            else:
                raise Exception('Centered bins have to be of equal width.')
            edges -= width/2.
            edges = np.concatenate([edges, [edges[-1]+width]])
        return values, edges


    @property
    def ndims(self):
        return len(self.edges)-1


    @property
    def xlim(self):
        if self.cyclic_range is not None:
            return (0, self.cyclic_range)
        else:
            return (min(self.edges), max(self.edges))


    @property
    def ylim(self):
        return (min(self.values), max(self.values))



class DataOverlay(DataLayer, Overlay):
    """
    A DataOverlay can contain a number of DataLayer objects, which are to be
    overlayed on one axis. When adding new DataLayers to the DataOverlay
    it ensures the DataLayers have the same x- and y-label and recomputes the
    axis limits.
    """

    def __init__(self, overlays, **kwargs):
        super(DataOverlay, self).__init__([], **kwargs)
        self.set(overlays)


    def add(self, layer):

        if isinstance(layer, Annotation): pass
        elif not len(self):
            self.xlim = layer.xlim
            self.ylim = layer.ylim
            self.xlabel = layer.xlabel
            self.ylabel = layer.ylabel
        else:
            self.xlim = find_minmax(self.xlim, layer.xlim)
            self.ylim = find_minmax(self.ylim, layer.ylim)
            if layer.xlabel != self.xlabel or layer.ylabel != self.ylabel:
                raise Exception("DataLayers must share common x- and y-labels.")
        self.data.append(layer)


    def cyclic_range(self):
        return self[0].cyclic_range



class Stack(NdMapping):
    """
    A Stack is a stack of Views over some dimensions. The
    dimension may be a spatial dimension (i.e., a ZStack), time
    (specifying a frame sequence) or any other dimensions.
    """

    title = param.String(default='{label} \n {dims}', doc="""
       A short description of the stack that may be used as a title
       (e.g. the title of an animation) but may also accept a
       formatting string to generate a unique title per layer.
       The formatters {label}, {type} and {dims} referring to
       the View lable, type and dimensions key/value pairs
       respectively.""")

    data_type = View
    overlay_type = Overlay

    _type = None
    _style = None

    @property
    def type(self):
        """
        The type of elements stored in the stack.
        """
        if self._type is None:
            self._type = None if len(self) == 0 else self.top.__class__
        return self._type


    @property
    def style(self):
        """
        The type of elements stored in the stack.
        """
        if self._style is None:
            self._style = None if len(self) == 0 else self.top.style
        return self._style


    @style.setter
    def style(self, style_name):
        self._style = style_name
        for val in self.values():
            val.style = style_name


    @property
    def empty_element(self):
        return self._type(None)


    def _item_check(self, dim_vals, data):
        if self.style is not None and self.style != data.style:
            data.style = self.style

        if self.type is not None and (type(data) != self.type):
            raise AssertionError("%s must only contain one type of View." %
                                 self.__class__.__name__)
        super(Stack, self)._item_check(dim_vals, data)
        self._set_title(dim_vals, data)


    def _set_title(self, key, item, group_size=2):
        """
        Sets a title string on the element item is added to the Stack, based on
        the element label and formatted stack dimensions and values.
        """
        if self.ndims == 1 and self.dim_dict.get('Default', False):
            return None
        dimension_labels = [dim.pprint_value(k) for dim, k in zip(self._dimensions, key)]
        groups = [', '.join(dimension_labels[i*group_size:(i+1)*group_size])
                      for i in range(len(dimension_labels))]
        dims = '\n '.join(g for g in groups if g)
        if isinstance(item, Overlay):
            for layer in item:
                format_dict = dict(dims=dims, label=layer.label, type=layer.__class__.__name__)
                layer.title = self.title.format(**format_dict)
        else:
            format_dict = dict(dims=dims, label=item.label, type=item.__class__.__name__)
            item.title = self.title.format(**format_dict)


    def split(self):
        """
        Given a SheetStack of SheetOverlays of N layers, split out the
        layers into N separate SheetStacks.
        """
        if self.type is not self.overlay_type:
            return self.clone(self.items())

        stacks = []
        item_stacks = defaultdict(list)
        for k, overlay in self.items():
            for i, el in enumerate(overlay):
                item_stacks[i].append((k, el))

        for k in sorted(item_stacks.keys()):
            stacks.append(self.clone(item_stacks[k]))
        return stacks


    def __mul__(self, other):
        if isinstance(other, self.__class__):
            self_set = set(self.dimension_labels)
            other_set = set(other.dimension_labels)

            # Determine which is the subset, to generate list of keys and
            # dimension labels for the new view
            self_in_other = self_set.issubset(other_set)
            other_in_self = other_set.issubset(self_set)
            dimensions = self.dimensions
            if self_in_other and other_in_self: # superset of each other
                super_keys = sorted(set(self.dimension_keys() + other.dimension_keys()))
            elif self_in_other: # self is superset
                dimensions = other.dimensions
                super_keys = other.dimension_keys()
            elif other_in_self: # self is superset
                super_keys = self.dimension_keys()
            else: # neither is superset
                raise Exception('One set of keys needs to be a strict subset of the other.')

            items = []
            for dim_keys in super_keys:
                # Generate keys for both subset and superset and sort them by the dimension index.
                self_key = tuple(k for p, k in sorted(
                    [(self.dim_index(dim), v) for dim, v in dim_keys
                     if dim in self.dimension_labels]))
                other_key = tuple(k for p, k in sorted(
                    [(other.dim_index(dim), v) for dim, v in dim_keys
                     if dim in other.dimension_labels]))
                new_key = self_key if other_in_self else other_key
                # Append SheetOverlay of combined items
                if (self_key in self) and (other_key in other):
                    items.append((new_key, self[self_key] * other[other_key]))
                elif self_key in self:
                    items.append((new_key, self[self_key] * other.empty_element))
                else:
                    items.append((new_key, self.empty_element * other[other_key]))
            return self.clone(items=items, dimensions=dimensions)
        elif isinstance(other, self.data_type):
            items = [(k, v * other) for (k, v) in self.items()]
            return self.clone(items=items)
        else:
            raise Exception("Can only overlay with {data} or {stack}.".format(
                data=self.data_type, stack=self.__class__.__name__))


    def __add__(self, obj):
        if not isinstance(obj, GridLayout):
            return GridLayout(initial_items=[self, obj])
        else:
            grid = GridLayout(initial_items=[self])
            grid.update(obj)
            return grid


    def __lshift__(self, other):
        if isinstance(other, (View, Overlay, NdMapping)):
            return Layout([self, other])
        elif isinstance(other, Layout):
            return Layout(other.data+[self])
        else:
            raise TypeError('Cannot append {0} to a Layout'.format(type(other).__name__))



    def _split_keys_by_axis(self, keys, x_axis):
        """
        Select an axis by name, returning the keys along the chosen
        axis and the corresponding shortened tuple keys.
        """
        x_ndim = self.dim_index(x_axis)
        xvals = [k[x_ndim] for k in keys]
        dim_vals = [k[:x_ndim] + k[x_ndim+1:] for k in keys]
        return list(map_type.fromkeys(xvals)), list(map_type.fromkeys(dim_vals))


    def split_axis(self, x_axis):
        """
        Returns all stored views such that the specified x_axis
        is eliminated from the full set of stack keys (i.e. each tuple
        key has one element removed corresponding to eliminated dimension).

        As the set of reduced keys is a subset of the original data, each
        reduced key must store multiple x_axis values.

        The return value is an OrderedDict with reduced tuples keys and
        OrderedDict x_axis values (views).
        """

        self._check_key_type = False # Speed optimization

        x_ndim = self.dim_index(x_axis)
        keys = self._data.keys()
        x_vals, dim_values = self._split_keys_by_axis(keys, x_axis)

        split_data = map_type()

        for k in dim_values:  # The shortened keys
            split_data[k] = map_type()
            for x in x_vals:  # For a given x_axis value...
                              # Generate a candidate expanded key
                expanded_key = k[:x_ndim] + (x,) + k[x_ndim:]
                if expanded_key in keys:  # If the expanded key actually exists...
                    split_data[k][x] = self[expanded_key]

        self._check_key_type = True # Re-enable checks
        return split_data


    def _compute_samples(self, samples):
        """
        Transform samples as specified to a format suitable for _get_sample.

        May be overridden to compute transformation from sheetcoordinates to matrix
        coordinates in single pass as an optimization.
        """
        return samples


    def _get_sample(self, view, sample):
        """
        Given a sample as processed by _compute_sample to extract a scalar sample
        value from the view. Uses __getitem__ by default but can operate on the view's
        data attribute if this helps optimize performance.
        """
        return view[sample]


    def _curve_labels(self, x_axis, sample, ylabel):
        """
        Given the x_axis, sample name and ylabel, returns the formatted curve
        label xlabel and ylabel for a curve. Allows changing the curve labels
        in subclasses of stack.
        """
        return str(sample), x_axis.capitalize(), sample


    def sample(self, samples=[], x_axis=None, group_by=[]):
        if x_axis is None and len(self.dimensions) > 1:
            raise Exception('Please specify the x_axis.')
        elif x_axis is None:
            x_axis = self.dimension_labels[0]

        x_dim = self.dim_dict[x_axis]
        specified_dims = [x_axis] + group_by
        specified_dims_set = set(specified_dims)

        if len(specified_dims) != len(specified_dims_set):
            raise Exception('X axis cannot be included in grouped dimensions.')

        # Dimensions of the output stack
        stack_dims = [d for d in self._dimensions if d.name not in specified_dims_set]

       # Get x_axis and non-x_axis dimension values
        split_data = self.split_axis(x_axis)

        # Everything except x_axis
        output_dims = [d for d in self.dimension_labels if d != x_axis]
        # Overlays as indexed with the x_axis removed
        overlay_inds = [i for i, name in enumerate(output_dims) if name in group_by]

        cyclic_range = x_dim.range[1] if x_dim.cyclic else None

        stacks = []
        for sample_ind, sample in enumerate(self._compute_samples(samples)):
            stack = DataStack(dimensions=stack_dims, metadata=self.metadata,
                              title=self.title)
            for key, x_axis_data in split_data.items():
                # Key contains all dimensions (including overlaid dimensions) except for x_axis
                sampled_curve_data = [(x, self._get_sample(view, sample))
                                      for x, view in x_axis_data.items()]

                # Compute overlay dimensions
                overlay_items = [(name, key[ind]) for name, ind in zip(group_by,
                                                                       overlay_inds)]


                # Generate labels
                legend_label = ', '.join(self.dim_dict[name].pprint_value(val)
                                         for name, val in overlay_items)
                ylabel = x_axis_data.values()[0].label
                label, xlabel, ylabel = self._curve_labels(x_axis,
                                                           samples[sample_ind],
                                                           ylabel)

                # Generate the curve view
                curve = Curve(sampled_curve_data, cyclic_range=cyclic_range,
                              metadata=self.metadata, label=label,
                              legend_label=legend_label, xlabel=xlabel,
                              ylabel=ylabel)

                # Drop overlay dimensions
                stack_key = tuple([kval for ind, kval in enumerate(key)
                                   if ind not in overlay_inds])

                # Create new overlay if necessary, otherwise add to overlay
                if stack_key not in stack:
                    stack[stack_key] = DataOverlay([curve])
                else:
                    stack[stack_key] *= curve

            # Completed stack stored for return
            stacks.append(stack)

        if len(stacks) == 1:  return stacks[0]
        else:                 return GridLayout(stacks)


    @property
    def xlim(self):
        xlim = self.top.xlim
        for data in self.values():
            xlim = find_minmax(xlim, data.xlim)
        return xlim


    @property
    def ylim(self):
        ylim = self.top.ylim
        for data in self.values():
            ylim = find_minmax(ylim, data.ylim)
        return ylim


    @property
    def lbrt(self):
        l, r = self.xlim
        b, t = self.ylim
        return float(l), float(b), float(r), float(t)



class DataStack(Stack):
    """
    A DataStack can hold any number of DataLayers indexed by a list of
    dimension values. It also has a number of properties, which can find
    the x- and y-dimension limits and labels.
    """

    data_type = (DataLayer, Annotation)

    overlay_type = DataOverlay

    @property
    def xlabel(self):
        return self.top.xlabel

    @property
    def ylabel(self):
        return self.metadata.ylabel if hasattr(self.metadata, 'ylabel') else self.top.ylabel



class Table(View):
    """
    A tabular view type to allow convenient visualization of either a
    standard Python dictionary or an OrderedDict. If an OrderedDict is
    used, the headings will be kept in the correct order.
    """

    def __init__(self, data, **kwargs):

        if not all(isinstance(k, str) for k in data.keys()):
            raise Exception("Dictionary keys must be strings.")

        super(Table, self).__init__(data=data, **kwargs)

        # Assume OrderedDict if not a vanilla Python dict
        self.headings = self.data.keys()
        if type(self.data) == dict:
            self.headings = sorted(self.headings)

    @property
    def rows(self):
        return len(self.headings)

    @property
    def cols(self):
        return 2

    def __getitem__(self, heading):
        """
        Get the value associated with the given heading (key).
        """
        if heading not in self.headings:
            raise IndexError("%r not in available headings." % heading)
        return self.data[heading]


    def cell_value(self, row, col):
        """
        Get the stored value for a given row and column indices.
        """
        if col > 1:
            raise Exception("Only two columns available in a Table.")
        elif row >= self.rows:
            raise Exception("Maximum row index is %d" % len(self.headings)-1)
        elif col == 0:
            return self.headings[row]
        else:
            heading = self.headings[row]
            return self.data[heading]


    def cell_type(self, row, col):
        """
        Returns the cell type given a row and column index. The common
        basic cell types are 'data' and 'heading'.
        """
        if col == 0:  return 'heading'
        else:         return 'data'



class TableStack(Stack):
    """
    A TableStack may hold any number of TableViews indexed by a list
    of dimension values. It also allows the values of a particular
    cell to be sampled by name across any valid dimension.
    """
    _type = Table

    _type_map = None

    def _item_check(self, dim_vals, data):

        if self._type_map is None:
            self._type_map = dict((k,type(v)) for (k,v) in data.data.items())

        if set(self._type_map.keys()) != set(data.data.keys()):
            raise AssertionError("All TableViews in a TableStack must have"
                                 " a common set of  headings.")

        for k, v in data.data.items():
            if k not in self._type_map:
                self._type_map[k] = None
            elif type(v) != self._type_map[k]:
                self._type_map[k] = None

        super(TableStack, self)._item_check(dim_vals, data)


    def sample(self, samples=[], x_axis=None, group_by=[]):
        """
        Sample across the stored TableViews according the the headings
        specified in samples and across the specified x_axis.
        """
        sample_types = [int, float] + np.sctypes['float'] + np.sctypes['int']
        if not all(h in self._type_map.keys() for h in samples):
            raise Exception("Invalid list of heading samples.")

        for sample in samples:
            if self._type_map[sample] is None:
                raise Exception("Cannot sample inhomogenous type %r" % sample)
            if self._type_map[sample] not in sample_types:
                raise Exception("Cannot sample from type %r" % self._type_map[sample].__name__)

        return super(TableStack, self).sample(samples, x_axis, group_by)


__all__ = list(set([_k for _k,_v in locals().items() if isinstance(_v, type) and
                    (issubclass(_v, Stack) or issubclass(_v, View))]))
