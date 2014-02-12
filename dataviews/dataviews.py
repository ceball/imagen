import numpy as np

import param

from views import View, Stack, Overlay

class DataLayer(View):
    """
    General purpose DataLayer for holding data to be plotted along some
    axes. Subclasses can implement specialized containers for data such as
    curves, points, bars or surfaces.
    """

    xlabel = param.String(default='', doc="X-axis label")

    xlim = param.NumericTuple(default=(0, 0), doc="X-axis limits")

    ylabel = param.String(default='', doc="Y-axis label")

    ylim = param.NumericTuple(default=(0, 0), doc="Y-axis limits")

    labels = param.List(default=[], doc="Legend labels")

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

        return DataOverlay(overlays, style=self.style, metadata=self.metadata)



class DataCurves(DataLayer):
    """
    DataCurves can contain a list of curves with associated metadata and
    cyclic_range parameter to indicate with what periodicity the curve wraps.
    """

    cyclic_range = param.Number(default=None, allow_None=True)

    def __init__(self, data, **kwargs):
        data = [] if data is None else data
        super(DataCurves, self).__init__(data, **kwargs)


    def __getitem__(self, index):
        return self.data[index]


    def __len__(self):
        return len(self.data)


    def __iter__(self):
        i = 0
        while i < len(self):
            yield self[i]
            i += 1



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


    def _find_minmax(self, lims, olims):
        limzip = zip(list(lims), list(olims), [np.min, np.max])
        return tuple([fn([l, ol]) for l, ol, fn in limzip])


    def add(self, layer):
        if not len(self):
            self.xlim = layer.xlim
            self.ylim = layer.ylim
            self.xlabel = layer.xlabel
            self.ylabel = layer.ylabel
        else:
            self.xlim = self._find_minmax(self.xlim, layer.xlim)
            self.ylim = self._find_minmax(self.ylim, layer.ylim)
            if layer.xlabel != self.xlabel or layer.ylabel != self.ylabel:
                raise Exception("DataLayers must share common x- and y-labels.")

        self.data.append(layer)


    def cyclic_range(self):
        return self[0].cyclic_range



class DataStack(Stack):
    """
    A DataStack can hold any number of DataLayers indexed by a list of
    dimension values. It also has a number of properties, which can find
    the x- and y-dimension limits and labels.
    """

    data_type = DataLayer

    overlay_type = DataOverlay

    def _find_minmax(self, lims, olims):
        limzip = zip(list(lims), list(olims), [np.min, np.max])
        return tuple([fn([l, ol]) for l, ol, fn in limzip])

    @property
    def xlim(self):
        xlim = self.top.xlim
        for data in self.values():
            xlim = self._find_minmax(xlim, data.xlim)
        return xlim

    @property
    def ylim(self):
        ylim = self.top.ylim
        for data in self.values():
            ylim = self._find_minmax(ylim, data.ylim)
        return ylim

    @property
    def lbrt(self):
        l, r = self.xlim
        b, t = self.ylim
        return float(l), float(b), float(r), float(t)

    @property
    def xlabel(self):
        return self.top.xlabel

    @property
    def ylabel(self):
        return self.metadata.ylabel if hasattr(self.metadata, 'ylabel') else self.top.ylabel


__all__ = list(set([_k for _k,_v in locals().items() if isinstance(_v, type) and
                    (issubclass(_v, Stack) or issubclass(_v, View))]))