# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from sgtk.platform.qt import QtGui, QtCore

from .shotgun_model import ShotgunModel
from .util import get_sg_data, get_sanitized_data
from .ui import resources_rc

class ShotgunEntityModel(ShotgunModel):
    """
    This model represents the data which is displayed inside one of the treeview tabs
    on the left hand side.
    """

    # global cache of step colours - avoids querying from Shotgun multiple times!
    _SG_STEP_COLOURS = {}

    def __init__(self, entity_type, filters, hierarchy, fields, parent, 
                 download_thumbs=False, schema_generation=0, bg_load_thumbs=False,
                 bg_task_manager=None):
        """
        Construction

        :param entity_type:         The type of the entities that should be loaded into this model.
        :param filters:             A list of filters to be applied to entities in the model - these 
                                    will be passed to the Shotgun API find() call when populating the 
                                    model
        :param hierarchy:           List of Shotgun fields that will be used to define the structure 
                                    of the items in the model.
        :param fields:              List of Shotgun fields to populate the items in the model with.
                                    These will be passed to the Shotgun API find() call when populating
                                    the model.
        :param parent:              Parent object.
        :param download_thumbs:     Boolean to indicate if this model should attempt
                                    to download and process thumbnails for the downloaded data.
        :param schema_generation:   Schema generation index. If you are changing the format
                                    of the data you are retrieving from Shotgun, and therefore
                                    want to invalidate any cache files that may already exist
                                    in the system, you can increment this integer.
        :param bg_load_thumbs:      If set to True, thumbnails will be loaded in the background.
        :param bg_task_manager:     Background task manager to use for any asynchronous work.  If
                                    this is None then a task manager will be created as needed.
        """
        self._entity_icons = {}
        self._step_swatch_icons = {}

        # make sure fields is valid:
        fields = fields or []
        # for backwards compatibility, make sure certain fields are added:
        fields = list(set(fields + ["image", "sg_status_list", "description"]))

        ## folder icon
        self._default_icon = QtGui.QIcon(QtGui.QPixmap(":/tk-framework-shotgunutils/icon_Folder.png"))

        ShotgunModel.__init__(self, 
                              parent = parent,
                              download_thumbs = download_thumbs,
                              schema_generation = schema_generation,
                              bg_load_thumbs = bg_load_thumbs,
                              bg_task_manager = bg_task_manager)

        # load the data from the cache:
        self._load_data(entity_type, filters, hierarchy, fields)

    def destroy(self):
        """
        Call to clean-up the model when it is finished with
        """
        ShotgunModel.destroy(self)
        self._entity_icons = {}
        self._step_swatch_icons = {}
        self._default_icon = None

    def get_entity_icon(self, entity_type):
        """
        Retrieve the icon for the specified entity type if available.

        :param entity_type: The entity type to retrieve the icon for
        :returns:           A QIcon if an icon was found for the specified entity
                            type, otherwise None.
        """
        icon = None
        if entity_type in self._entity_icons:
            # we've previously asked for the icon
            icon = self._entity_icons[entity_type]
        else:
            # see if we have the icon in the resources:
            icon_path = ":/tk-framework-shotgunutils/icon_%s_dark.png" % entity_type
            if QtCore.QFile.exists(icon_path): 
                # create the new icon from this resource:
                icon = QtGui.QIcon(QtGui.QPixmap(icon_path))
            self._entity_icons[entity_type] = icon

        return QtGui.QIcon(icon) if icon else None

    def get_entities(self, item):
        """
        Get entities for the current item by traversing up the tree and pulling 
        entity information from each item if possible

        :param item:    The item to find entities for
        :returns:       A list of entities in the order they were found starting
                        from the specified item.
        """
        entities = []
        current_item = item

        # first, if this is a leaf item then it will represent an entity:
        sg_data = current_item.get_sg_data()
        if sg_data:
            entities.append(sg_data)
            current_item = current_item.parent()

        # now walk up the tree and look for an entity in the fields of the 
        # parent items:
        while current_item:
            field_data = get_sanitized_data(current_item, self.SG_ASSOCIATED_FIELD_ROLE)
            field_value = field_data.get("value")
            if (field_value 
                and isinstance(field_value, dict) 
                and "id" in field_value 
                and "type" in field_value):
                entities.append(field_value)
            current_item = current_item.parent()

        return entities

    def get_entity(self, item):
        """
        Get the Shotgun entity details for the specified model item.

        :param item:    The item to retrieve the entity details for
        :returns:       A Shotgun entity dictionary for the item if it represents
                        and entity, otherwise None
        """
        sg_data = item.get_sg_data()
        if sg_data:
            return sg_data

        field_data = get_sanitized_data(item, self.SG_ASSOCIATED_FIELD_ROLE)
        field_value = field_data.get("value")
        if (field_value 
            and isinstance(field_value, dict) 
            and "id" in field_value 
            and "type" in field_value):
            return field_value

        return None

    def async_refresh(self):
        """
        Trigger an asynchronous refresh of the model
        """
        self._refresh_data()

    def _populate_default_thumbnail(self, item):
        """
        Whenever an item is constructed, this methods is called. It allows subclasses to intercept
        the construction of a QStandardItem and add additional metadata or make other changes
        that may be useful. Nothing needs to be returned.

        :param item: QStandardItem that is about to be added to the model. This has been primed
                     with the standard settings that the ShotgunModel handles.
        :param sg_data: Shotgun data dictionary that was received from Shotgun given the fields
                        and other settings specified in load_data()
        """
        found_icon = False

        # get the associated field data with this node
        field_data = get_sanitized_data(item, self.SG_ASSOCIATED_FIELD_ROLE)
        # get the full sg data for this node (leafs only)
        sg_data = get_sg_data(item)

        # {'name': 'sg_sequence', 'value': {'type': 'Sequence', 'id': 11, 'name': 'bunny_080'}}
        field_value = field_data["value"]

        if isinstance(field_value, dict) and "name" in field_value and "type" in field_value:
            # this is an intermediate node which is an entity type link
            entity_icon = self._get_default_thumbnail(field_value)
            if entity_icon:
                # use sg icon!
                item.setIcon(QtGui.QIcon(entity_icon))
                found_icon = True

        elif sg_data:
            # this is a leaf node!
            entity_icon = self._get_default_thumbnail(sg_data)
            if entity_icon:
                # use sg icon!
                item.setIcon(QtGui.QIcon(entity_icon))
                found_icon = True

        # for all items where we didn't find the icon, fall back onto the default
        if not found_icon:
            item.setIcon(QtGui.QIcon(self._default_icon))

    def _get_default_thumbnail(self, sg_entity):
        """
        Get the default icon for the specified entity.

        :param sg_entity:   A Shotgun entity dictionary for the entity to get the
                            icon for.
        :returns:           A QIcon for the entity if available.  For Step entities, a
                            swatch representing the step colour is returned.  If no
                            icon is available for the entity type then None is returned
        """
        if sg_entity.get("type") == "Step":
            # special case handling for steps to return a colour swatch:
            step_id = sg_entity.get("id")
            if step_id != None:
                # get the colour from the cache:
                if step_id not in ShotgunEntityModel._SG_STEP_COLOURS:
                    ShotgunEntityModel._SG_STEP_COLOURS[step_id] = None
                    # refresh cache:
                    bundle = sgtk.platform.current_bundle()
                    try:
                        sg_steps = bundle.shotgun.find("Step", [], ["color"])
                        for sg_step in sg_steps:
                            colour = None
                            try:
                                colour = tuple([int(c) for c in sg_step.get("color").split(",")])
                            except:
                                pass
                            ShotgunEntityModel._SG_STEP_COLOURS[sg_step["id"]] = colour  
                    except:
                        pass
                colour = ShotgunEntityModel._SG_STEP_COLOURS[step_id]

                if colour and isinstance(colour, tuple) and len(colour) == 3:
                    # get the icon for this colour from the cache:
                    if colour not in self._step_swatch_icons:
                        # build icon and add to cache:
                        pm = QtGui.QPixmap(16, 16)
                        pm.fill(QtCore.Qt.transparent)
                        painter = QtGui.QPainter(pm)
                        try:
                            painter.setBrush(QtGui.QBrush(QtGui.QColor(colour[0], colour[1], colour[2])))
                            painter.setPen(QtCore.Qt.black)
                            painter.drawRect(2, 2, 12, 12)
                        finally:
                            painter.end()
                        self._step_swatch_icons[colour] = QtGui.QIcon(pm)

                    # return the icon:
                    return QtGui.QIcon(self._step_swatch_icons[colour])

        # just return the entity icon:
        return self.get_entity_icon(sg_entity.get("type"))

