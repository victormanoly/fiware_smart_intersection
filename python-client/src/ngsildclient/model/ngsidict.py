#!/usr/bin/env python3

# Software Name: ngsildclient
# SPDX-FileCopyrightText: Copyright (c) 2021 Orange
# SPDX-License-Identifier: Apache 2.0
#
# This software is distributed under the Apache 2.0;
# see the NOTICE file for more details.
#
# Author: Fabien BATTELLO <fabien.battello@orange.com> et al.

from __future__ import annotations

from typing import Any, Union, List
from functools import reduce
from datetime import datetime
from geojson import Point, LineString, Polygon, MultiPoint

import ngsildclient.model.entity as entity
from ..utils import iso8601, url
from ..utils.urn import Urn
from .constants import *
from .exceptions import *

import json
import operator

"""This module contains the definition of the NgsiDict class.
"""


class NgsiDict(dict):
    """This class is a custom dictionary that backs an entity.

    NgsiDict is used to build and hold the entity properties, as well as the entity's root.
    It's not exposed to the user but intended to be used by the Entity class.
    NgsiDict provides methods that allow to build a dictionary compliant with a NGSI-LD structure.

    See Also
    --------
    model.Entity
    """

    def __init__(self, *args, dtcached: datetime = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._dtcached: datetime = dtcached if dtcached else iso8601.utcnow()

    @classmethod
    def _from_json(cls, payload: str):
        d = json.loads(payload)
        return cls(d)

    def _cachedate(self, dt: datetime):
        self._dtcached = dt

    def _dateauto(self):
        if self._dtcached is None:
            self._dtcached = iso8601.utcnow()
        return self._dtcached

    def __getitem__(self, element: str):
        return reduce(dict.__getitem__, element.split("."), self)

    def __delitem__(self, element: str):
        try:
            nested, k = element.rsplit(".", 1)
        except ValueError:
            dict.__delitem__(self, element)
        else:
            dict.__delitem__(self[nested], k)

    def __setitem__(self, key: str, value: Any):
        try:
            nested, k = key.rsplit(".", 1)
        except ValueError:
            dict.__setitem__(self, key, value)
        else:
            dict.__setitem__(self[nested], k, value)

    @classmethod
    def _load(cls, filename: str):
        with open(filename, "r") as fp:
            d = json.load(fp)
            return cls(d)

    def to_json(self, indent=None) -> str:
        """Returns the dict in json format"""
        return json.dumps(self, default=str, ensure_ascii=False, indent=indent)

    def pprint(self, *args, **kwargs) -> None:
        """Returns the dict pretty-json-formatted"""
        print(self.to_json(indent=2, *args, **kwargs))

    def _save(self, filename: str, indent=2):
        with open(filename, "w") as fp:
            json.dump(self, fp, default=str, ensure_ascii=False, indent=indent)

    def _process_observedat(self, observedat):
        if observedat is Auto:
            observedat = self._dateauto()
        date_str, temporaltype, dt = iso8601.parse(observedat)
        if temporaltype != TemporalType.DATETIME:
            raise NgsiDateFormatError(f"observedAt must be a DateTime : {date_str}")
        self._cachedate(dt)
        return date_str

    def _build_property(
        self,
        value: Any,
        unitcode: str = None,
        observedat: Union[str, datetime, type[Auto]] = None,
        datasetid: str = None,
        userdata: NgsiDict = None,
        escape: bool = False,
    ) -> NgsiDict:
        property: NgsiDict = NgsiDict()
        property["type"] = AttrType.PROP.value  # set type
        if isinstance(value, (int, float, bool, list, dict)):
            v = value
        elif isinstance(value, str):
            v = url.escape(value) if escape else value
        else:
            raise NgsiUnmatchedAttributeTypeError(f"Cannot map {type(value)} to NGSI type. {value=}")
        property["value"] = v  # set value
        if unitcode is not None:
            property[META_ATTR_UNITCODE] = unitcode
        if observedat is not None:
            property[META_ATTR_OBSERVED_AT] = self._process_observedat(observedat)
        if datasetid is not None:
            property[META_ATTR_DATASET_ID] = Urn.prefix(datasetid)
        if userdata:
            property |= userdata
        return property

    def prop(self, name: str, value: str, **kwargs):
        self[name] = self._build_property(value, **kwargs)
        return self[name]

    def _build_geoproperty(
        self,
        value: NgsiGeometry,
        observedat: Union[str, datetime, type[Auto]] = None,
        datasetid: str = None,
    ) -> NgsiDict:
        property: NgsiDict = NgsiDict()
        property["type"] = AttrType.GEO.value  # set type
        if isinstance(value, (Point, LineString, Polygon, MultiPoint)):
            geometry = value
        elif isinstance(value, tuple) and len(value) == 2:  # simple way for a location Point
            lat, lon = value
            geometry = Point((lon, lat))
        else:
            raise NgsiUnmatchedAttributeTypeError(f"Cannot map {type(value)} to NGSI type. {value=}")
        property["value"] = geometry  # set value
        if observedat is not None:
            property[META_ATTR_OBSERVED_AT] = self._process_observedat(observedat)
        if datasetid is not None:
            property[META_ATTR_DATASET_ID] = Urn.prefix(datasetid)
        return property

    def gprop(self, name: str, value: str, **kwargs):
        self[name] = self._build_geoproperty(value, **kwargs)
        return self[name]

    def _build_temporal_property(self, value: Union[NgsiDate, type[Auto]]) -> NgsiDict:
        property: NgsiDict = NgsiDict()
        property["type"] = AttrType.TEMPORAL.value  # set type

        if value is Auto:
            value = self._dateauto()

        date_str, temporaltype, dt = iso8601.parse(value)
        v = {
            "@type": temporaltype.value,
            "@value": date_str,
        }
        property["value"] = v  # set value
        self._cachedate(dt)
        return property

    def tprop(self, name: str, value: str, **kwargs):
        self[name] = self._build_temporal_property(value, **kwargs)
        return self[name]

    def _build_relationship(
        self,
        value: Union[str, List[str]],
        observedat: Union[str, datetime, type[Auto]] = None,
        datasetid: str = None,
        userdata: NgsiDict = None,
    ) -> NgsiDict:
        property: NgsiDict = NgsiDict()
        property["type"] = AttrType.REL.value  # set types
        property["object"] = Urn.prefix(value.id) if isinstance(value, entity.Entity) else Urn.prefix(value)
        if observedat is not None:
            property[META_ATTR_OBSERVED_AT] = self._process_observedat(observedat)
        if datasetid is not None:
            property[META_ATTR_DATASET_ID] = Urn.prefix(datasetid)
            if userdata:
                property |= userdata
        return property

    def _m_build_relationship(
        # Multiple Relationship limitation : no metadata
        self,
        value: List[str],
        observedat: Union[str, datetime, type[Auto]] = None,
        datasetid: str = None,
        userdata: NgsiDict = None,
    ) -> NgsiDict:
        property: List[NgsiDict] = []
        if isinstance(observedat, List):
            if len(observedat) != len(value):
                raise ValueError("Missing observedAt attributes")
        else:
            observedat = [observedat] * len(value)
        if isinstance(datasetid, List):
            if len(datasetid) != len(value):
                raise ValueError("Missing datasetId attributes")
        else:
            datasetid = [datasetid] * len(value)
        if isinstance(userdata, List):
            if len(userdata) != len(value):
                raise ValueError("Missing userdata attributes")
        else:
            userdata = [userdata] * len(value)
        for x in zip(value, observedat, datasetid, userdata):
            property.append(self._build_relationship(*x))
        return property

    def rel(self, name: str, value: str, **kwargs):
        if isinstance(name, Rel):
            name = name.value
        self[name] = self._build_relationship(value, **kwargs)
        return self[name]
