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
from typing import TYPE_CHECKING, Optional

import logging

if TYPE_CHECKING:
    from .client import Client

from .constants import *
from .exceptions import (
    NgsiAlreadyExistsError,
    NgsiApiError,
    rfc7807_error_handle
)
from ..model.entity import Entity


logger = logging.getLogger(__name__)


class Entities:
    def __init__(self, client: Client, url: str):
        self._client = client
        self._session = client.session
        self.url = url

    @rfc7807_error_handle
    def create(
        self,
        entity: Entity,
        skip: bool = False,
        overwrite: bool = False
    ) -> Optional[Entity]:
        r = self._session.post(
            f"{self.url}/",
            json=entity._payload,
        )

        if r.status_code == 409:  # already exists
            if skip:
                return None
            elif overwrite or self._client.overwrite:
                return self.update(entity, check_exists=False)

        self._client.raise_for_status(r)
        location = r.headers.get("Location")
        if location is None:
            if self._client.ignore_errors:
                return None
            else:
                raise NgsiApiError("Missing Location header")
        logger.info(f"{r.status_code=}")
        logger.info(f"{location=}")
        id_returned_from_broker = location.rsplit("/", 1)[-1]
        if entity.id != id_returned_from_broker:
            raise NgsiApiError(
                f"Broker returned wrong id. Expected={entity.id} Returned={id_returned_from_broker}"
            )
        return entity

    @rfc7807_error_handle
    def get(
        self,
        eid: Union[EntityId, Entity],
        ctx: str = None,
        asdict: bool = False,
        **kwargs,
    ) -> Entity:
        eid = eid.id if isinstance(eid, Entity) else eid
        headers = {
            "Accept": "application/ld+json",
            "Content-Type": None,
        }  # overrides session headers
        if ctx is not None:
            headers[
                "Link"
            ] = f'<{ctx}>; rel="{JSONLD_CONTEXT}"; type="application/ld+json"'
        r = self._session.get(f"{self.url}/{eid}", headers=headers, **kwargs)
        self._client.raise_for_status(r)
        return r.json() if asdict else Entity.from_dict(r.json())

    @rfc7807_error_handle
    def delete(self, eid: Union[EntityId, Entity]) -> bool:
        eid = eid.id if isinstance(eid, Entity) else eid
        logger.info(f"{eid=}")
        logger.info(f"url={self.url}/{eid}")
        r = self._session.delete(f"{self.url}/{eid}")
        logger.info(f"requests: {r.request.url}")
        self._client.raise_for_status(r)
        return bool(r)

    @rfc7807_error_handle
    def exists(self, eid: Union[EntityId, Entity]) -> bool:
        eid = eid.id if isinstance(eid, Entity) else eid
        r = self._session.get(f"{self.url}/{eid}")
        if r:
            payload = r.json()
            return "@context" in payload
        return False

    @rfc7807_error_handle
    def upsert(self, entity: Entity) -> Entity:
        try:
            return self.create(entity)
        except NgsiAlreadyExistsError:
            self.delete(entity)
            return self.create(entity)

    @rfc7807_error_handle
    def update(self, entity: Entity, check_exists: bool = True) -> Optional[Entity]:
        if check_exists and self.exists(entity):
            self.delete(entity)
            return self.create(entity)
        return None

    @rfc7807_error_handle
    def query(
        self,
        type: str = None,
        q: str = None,
        ctx: str = None,
        limit: int = 0,
        offset: int = 0,
        **kwargs,
    ) -> List[Entity]:
        params = {}
        if limit != 0:
            params |= {"limit": limit}
        if offset != 0:
            params |= {"offset": offset}
        if type is None and q is None:
            raise ValueError("Must indicate at least a type or a query string")
        if type:
            params["type"] = type
        if q:
            params["q"] = q
        headers = {
            "Accept": "application/ld+json",
            "Content-Type": None,
        }  # overrides session headers
        if ctx is not None:
            headers[
                "Link"
            ] = f'<{ctx}>; rel="{JSONLD_CONTEXT}"; type="application/ld+json"'
        r = self._session.get(
            self.url,
            headers=headers,
            params=params,
        )
        r.raise_for_status()
        self._client.raise_for_status(r)
        entities = r.json()
        logger.debug(f"{entities=}")
        return [Entity.from_dict(entity) for entity in entities]

    @rfc7807_error_handle
    def count(self, type: str = None, q: str = None, **kwargs) -> int:
        params = {"limit": 0, "count": "true"}
        if type is None and q is None:
            raise ValueError("Must indicate at least a type or a query string")
        if type:
            params["type"] = type
        if q:
            params["q"] = q
        r = self._session.get(
            self.url,
            headers={
                "Accept": "application/json",
                "Content-Type": None,
            },  # overrides session headers
            params=params,
        )
        r.raise_for_status()
        self._client.raise_for_status(r)
        count = int(r.headers["NGSILD-Results-Count"])
        return count
