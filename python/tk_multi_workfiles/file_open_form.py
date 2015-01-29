# Copyright (c) 2014 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Qt widget that presents the user with a list of work files and publishes
so that they can choose one to open
"""

import copy

import sgtk
from sgtk.platform.qt import QtCore, QtGui
from sgtk import TankError

from .ui.file_open_form import Ui_FileOpenForm
from .entity_tree_form import EntityTreeForm
from .my_tasks_form import MyTasksForm
from .file_list_form import FileListForm

shotgun_model = sgtk.platform.import_framework("tk-framework-shotgunutils", "shotgun_model")
ShotgunEntityModel = shotgun_model.ShotgunEntityModel
ShotgunModel = shotgun_model.ShotgunModel
shotgun_data = sgtk.platform.import_framework("tk-framework-shotgunutils", "shotgun_data")
ShotgunDataRetriever = shotgun_data.ShotgunDataRetriever

from .publishes_proxy_model import PublishesProxyModel
from .work_files_proxy_model import WorkFilesProxyModel

class MyTasksModel(ShotgunEntityModel):
    """
    """
    _MAX_THUMB_WIDTH=512
    _MAX_THUMB_HEIGHT=512
    
    def __init__(self, filters, parent=None):
        """
        """
        ShotgunModel.__init__(self, parent, download_thumbs=True)
        
        fields = ["image", "sg_status_list", "description", "entity", "content"]
        self._load_data("Task", filters, ["id"], fields)
    
    def _populate_default_thumbnail(self, item):
        """
        """
        pass
    
    def _populate_thumbnail(self, item, field, path):
        """
        """
        if field != "image":
            # there may be other thumbnails being loaded in as part of the data flow
            # (in particular, created_by.HumanUser.image) - these ones we just want to 
            # ignore and not display.
            return
    
        # set the item icon to be the thumbnail:
        item.setIcon(QtGui.QIcon(path))

class EntitySearchDetails(object):
    def __init__(self, name, sg_entity=None, context=None, publish_filters=None):
        self.name = name
        self.entity = sg_entity
        self.context = context
        self.publish_filters = publish_filters
        self.children = []
        
    def __repr__(self):
        return "%s\nFilters: %s\nContext: %s\n - %s" % (self.name, self.publish_filters, self.context, self.children)

class FileOpenForm(QtGui.QWidget):
    """
    UI for opening a publish or work file.  Presents a list of available files to the user
    so that they can choose one to open in addition to any other user-definable actions.
    """
    
    @property
    def exit_code(self):
        return self._exit_code    
    
    def __init__(self, init_callback, parent=None):
        """
        Construction
        """
        QtGui.QWidget.__init__(self, parent)
        
        # set up the UI
        self._ui = Ui_FileOpenForm()
        self._ui.setupUi(self)

        # create a single instance of a ShotgunDataRetriever that will be used to
        # download all thumbnails in the background
        #self._sg_data_retriever = ShotgunDataRetriever(self)
        
        # initialize task trees:
        self._initilize_task_trees()
             
        # initialize the file views:
        self._initilize_file_views()
                
        # hook up all other controls:
        self._ui.cancel_btn.clicked.connect(self._on_cancel)

        self.__context_cache = {}

        # call init callback:
        init_callback(self)
        
    def closeEvent(self, event):
        """
        """
        # stop the Shotgun data retriever:
        #self._sg_data_retriever.stop()
        
        return QtGui.QWidget.closeEvent(self, event)

    def _initilize_task_trees(self):
        """
        Initialize the task trees
        """
        app = sgtk.platform.current_bundle()

        # set up 'My Tasks':        
        if app.context.user:
            filters = [["project", "is", app.context.project],
                       ["task_assignees", "is", app.context.user]]
            
            model = MyTasksModel(filters, self)
            model.async_refresh()
            
            # create my tasks form:
            my_tasks_form = MyTasksForm(model, self)
            my_tasks_form.task_selected.connect(self._on_my_task_selected)
            self._ui.task_browser_tabs.addTab(my_tasks_form, "My Tasks")
        
        # set up any defined task trees:
        entities = app.get_setting("entities", [])
        for ent in entities:
            caption = ent.get("caption", None)
            entity_type = ent.get("entity_type")
            filters = ent.get("filters")
            
            # resolve any magic tokens in the filter
            resolved_filters = []
            for filter in filters:
                resolved_filter = []
                for field in filter:
                    if field == "{context.project}":
                        field = app.context.project
                    elif field == "{context.entity}":
                        field = app.context.entity
                    elif field == "{context.step}":
                        field = app.context.step
                    elif field == "{context.task}":
                        field = app.context.task
                    elif field == "{context.user}":
                        field = app.context.user
                    resolved_filter.append(field)
                resolved_filters.append(resolved_filter)
                            
            hierarchy = ent.get("hierarchy")
            
            # create an entity model for this query:
            model = ShotgunEntityModel(entity_type, resolved_filters, hierarchy, parent=self)
            model.async_refresh()
            
            # create new entity form:
            entity_form = EntityTreeForm(model, caption, self)
            entity_form.entity_selected.connect(self._on_entity_selected)
            self._ui.task_browser_tabs.addTab(entity_form, caption)
        
    def _initilize_file_views(self):
        """
        """
        app = sgtk.platform.current_bundle()
        
        # create the model that represents all files:
        self._file_model = FileModel(self)

        # add an 'all files' tab:
        all_files_form = FileListForm("All Files", self)
        self._ui.file_browser_tabs.addTab(all_files_form, "All")
        all_files_form.set_model(self._file_model)
        
        # create the workfiles proxy model & form:
        work_files_model = WorkFilesProxyModel(self)
        work_files_model.setSourceModel(self._file_model)
        work_files_form = FileListForm("Work Files", self)
        work_files_form.set_model(work_files_model)
        self._ui.file_browser_tabs.addTab(work_files_form, "Working")

        # create the publish proxy model & form:
        publishes_model = PublishesProxyModel(self)
        publishes_model.setSourceModel(self._file_model)
        publishes_form = FileListForm("Publishes", self)
        publishes_form.set_model(publishes_model)
        self._ui.file_browser_tabs.addTab(publishes_form, "Publishes")
        
        # create any user-sandbox/configured tabs:
        # (AD) TODO
        
    def _on_my_task_selected(self, task_index):
        """
        """
        if not task_index:
            return None
        
        app = sgtk.platform.current_bundle()
        
        # get the item for the specified index:
        task_item = task_index.model().itemFromIndex(task_index)
        
        # find the publish filters and context for this item:
        publish_filters = self._extract_publish_filters(task_item)
        context = self._extract_context(task_item)

        # finally, update the file model for the filters and context:
        self._file_model.refresh_files(publish_filters, context)        
        
    def _on_entity_selected(self, entity_index):
        """
        Called when something has been selected in an entity tree view.  From 
        this selection, a list of publishes and work files can then be found
        which will be used to populate the main file grid/details view.
        """
        if not entity_index:
            return None
        
        # get the item for the specified index:
        entity_item = entity_index.model().itemFromIndex(entity_index)

        # extract the search details from this item that will be used to search for files:
        item_details = self._get_search_details_for_item(entity_item)
        
        # now iterate over immediate children finding search details for them.  There is a special
        # case handling for Step children that have immediate Task children
        for ri in range(entity_item.rowCount()):
            child_item = entity_item.child(ri)
            child_details = self._get_search_details_for_item(child_item)

            collapsed_steps = False
            if child_details.step and not child_details.entity and not child_details.is_leaf:
                # child is a Step and not a leaf so special case if grandchildren are leaf tasks 
                # as we can collapse step and task together:
                for cri in range(child_item.rowCount()):
                    grandchild_item = child_item.child(cri)
                    grandchild_details = self._get_search_details_for_item(grandchild_item)
                    if (grandchild_details.is_leaf 
                        and not grandchild_details.entity 
                        and grandchild_details.task):
                        # have a leaf level task under a step!
                        grandchild_details.name = "%s - %s" % (child_details.name, grandchild_details.name)
                        item_details.children.append(grandchild_details)
                        collapsed_steps = True

            if not collapsed_steps:
                item_details.children.append(child_details)

        print "B"

        self._file_model.refresh_files(item_details)

        print "C"
        

    def _get_search_details_for_item(self, item):
        """
        """
        app = sgtk.platform.current_bundle()
        
        class _Details(object):
            def __init__(self, item):
                """
                """
                self.item = item
                self.entity = None
                self.task = None
                self.step = None
                self.is_leaf = False
                self.children = []
                self.name = item.text() if item else ""
                
            def __repr__(self):
                return ("%s\n"
                        " - Entity: %s\n"
                        " - Task: %s\n"
                        " - Step: %s\n"
                        " - Is leaf: %s\n%s"
                        % (self.name, self.entity, self.task, self.step, self.is_leaf, self.children))

        details = _Details(item)
        
        model = item.model()
        item_entity = model.get_entity(item)
        if not item_entity:
            return details
        
        item_entity = {"type":item_entity["type"], "id":item_entity["id"]}
        entity_type = item_entity["type"]

        if item.rowCount() == 0 and entity_type == model.get_entity_type():
            details.is_leaf = True
        
        if entity_type == "Task":
            details.task = item_entity
        elif entity_type == "Step":
            details.step = item_entity
        else:
            details.entity = item_entity
            
            # see if we can find a task or step as well:
            parent_item = item.parent()
            while parent_item:
                parent_entity = model.get_entity(parent_item)
                if parent_entity:
                    parent_entity = {"type":parent_entity["type"], "id":parent_entity["id"]}
                    parent_entity_type = parent_entity["type"]
                    if parent_entity_type == "Task":
                        # found a specific task!
                        details.task = parent_entity
                        details.step = None
                        # this is the best we can do so lets stop looking!                        
                        break
                    elif parent_entity_type == "Step":
                        # found a specific step!
                        details.step = parent_entity
                        # don't break as we would prefer to find a task entity!            

                parent_item = parent_item.parent()

        return details
        
    def _extract_context(self, entity_item):
        """
        """
        app = sgtk.platform.current_bundle()

        # get the list of entities for the item:
        entities = entity_item.model().get_entities(entity_item)
            
        # from the list of entities, extract a context:
        context_project = None
        context_entity = None
        context_task = None
        for entity in entities:
            entity_type = entity.get("type")
            if entity_type == "Task":
                context_task = context_task or entity
            elif entity_type == "Project":
                context_project = context_project or entity
            elif entity_type:
                context_entity = context_entity or entity
                
        entity_to_use = context_task or context_entity or context_project
        context = None
        if entity_to_use:
            try:
                cache_key = (entity_to_use["type"], entity_to_use["id"])
                if cache_key in self.__context_cache:
                    context =  self.__context_cache[cache_key]
                else:
                    # Note - context_from_entity is _really_ slow :(
                    # TODO: profile it to see if it can be improved!
                    context = app.sgtk.context_from_entity(entity_to_use["type"], entity_to_use["id"])
                    self.__context_cache[cache_key] = context
            except TankError, e:
                app.log_debug("Failed to create context from entity '%s'" % entity_to_use)
                
        return context

    def _extract_publish_filters(self, entity_item):
        """
        """
        app = sgtk.platform.current_bundle()

        # get the list of filters for the item:
        entity_model = entity_item.model()
        filters = entity_model.get_filters(entity_item)
        entity_type = entity_model.get_entity_type()
        
        # if we are on a leaf item then sg_data will represent a 
        # specific entity so add this to the filters:
        sg_data = entity_item.get_sg_data()
        if sg_data:
            filters = [["id", "is", sg_data["id"]]] + filters

        # all filters will be relative to the PublishedFile
        # entity so we need to extend the filters to either the 
        # linked entity or task:
        link_field = "task" if entity_type == "Task" else "entity"
        publish_filters = []
        for filter in copy.deepcopy(filters):
            filter[0] = "%s.%s.%s" % (link_field, entity_type, filter[0])
            publish_filters.append(filter)
            
        return publish_filters
        
        
    def _on_cancel(self):
        """
        Called when the cancel button is clicked
        """
        self._exit_code = QtGui.QDialog.Rejected        
        self.close()
        
        