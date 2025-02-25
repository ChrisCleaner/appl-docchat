import re
from os import remove, path, makedirs
from datetime import datetime
from shutil import rmtree
from flask import url_for, redirect, flash, Markup
from sqlalchemy import text

from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField, SubmitField, IntegerField, SelectField, BooleanField
from wtforms.validators import Length, ValidationError

from flask_app.models import db, Chat, ChatQuestion, DocSet, DocSetFile, UserGroup
from flask_app.helpers import render_chat_template, size_to_human, upload_file

from langchain.vectorstores import Chroma
from langchain.embeddings.openai import OpenAIEmbeddings

'''
This form contains all for inserting, updating and deleting a docset
'''

class DocSetForm(FlaskForm):

    # Field definitions
    id = HiddenField('ID', default=0)
    name = StringField('Name', default='', validators=[Length(min=3, max=64)], render_kw={'size': 40})
    llm_type = SelectField('LLM type', default='chatopenai', choices=['chatopenai'])
    llm_modeltype = SelectField('LLM model type', default='gpt35', choices=['gpt35', 'gpt35_16', 'gpt4'])
    embeddings_provider = SelectField('Embeddings provider', default='openai', choices=['openai'])
    embeddings_model = SelectField('Embeddings model', default='text-embedding-ada-002', choices=['text-embedding-ada-002'])
    chain = SelectField('Chain', default='conversationalretrievalchain', choices=['conversationalretrievalchain'])
    chain_type = SelectField('Chain type', default='stuff', choices=['stuff'])
    chain_verbosity = BooleanField('Chain verbosity', default=False, render_kw={'class': 'yes-checkbox'})
    search_type = SelectField('Search type', default='similarity', choices=['similarity'])
    vecdb_type = SelectField('Vector database', default='chromadb', choices=['chromadb'])
    chunk_size = IntegerField('Chunk size', default=1000, render_kw={'min': 100, 'max': 5000, 'step': 100})
    chunk_overlap = IntegerField('Chunk overlap', default=200)
    chunk_k = IntegerField('Chunk k', default=4)
    submit = SubmitField('Save')


    # Custom validation    ( See: https://wtforms.readthedocs.io/en/stable/validators/ )
    def validate_path(form, field):
        if not re.search(r'^[a-z0-9-]+$', field.data):
            raise ValidationError('Invalid name; Only lowercase, digits and - allowed.')


    # Handle the request (from routes.py) for this form
    def handle_request(self, method, id):

        # Show the form
        if method == 'GET':
            usergroups, checked, files = [], [], []
            if id > 0:
                # Get record from database and set the form values (if id == 0 the defaults are used)
                obj = DocSet.query.get(id)
                obj.fields_to_form(self)

                files, files_ = [], DocSetFile.query.filter(DocSetFile.docset_id == id).order_by(DocSetFile.no).all()
                for file in files_:
                    file_full_name = path.join(obj.get_doc_path(), file.filename)
                    files.append({
                        'id': file.id, 
                        'no': file.no, 
                        'name': file.filename, 
                        'dt': datetime.fromtimestamp(path.getctime(file_full_name)).strftime('%d-%m-%Y %H:%M:%S'),
                        'size': size_to_human(path.getsize(file_full_name)),
                    })

                # Get user groups with permission for this docset
                usergroups = db.session.execute(text('SELECT id, name, docset_' + str(id) + ' FROM ' + UserGroup.__tablename__ + ';')).fetchall()
                for usergroup in usergroups:
                    if getattr(usergroup, 'docset_' + str(id)) == 1:
                        checked.append('checked="checked"')
                    else:
                        checked.append('')
            # Show the form
            return render_chat_template('docset.html', form=self, usergroups = usergroups, checked=checked, files=files)
        
        # Save the form
        if method == 'POST':
            if self.validate():
                if id >= 1:
                    # The table needs to be updated with the new values
                    obj = DocSet.query.get(id)
                    obj.fields_from_form(self)
                    db.session.commit()

                    self.setUserGroupFields()

                    flash('The document set is saved.', 'info')
                    return redirect(url_for('docsets'))

                # A new record must be inserted in tyhe table
                obj = DocSet()
                obj.fields_from_form(self)
                db.session.add(obj)
                db.session.commit()
                id = obj.id

                makedirs(obj.get_doc_path(), exist_ok=True)
                
                self.setUserGroupFields()

                flash('The document set is saved.', 'info')
                return redirect(url_for('docset', id=id))
            
            # Validation failed: Show the form with the errors
            return render_chat_template('docset.html', form=self)

        # Show the files from the docset
        if method == 'FILES':
            obj = DocSet.query.get(id)
            obj.fields_to_form(self)
            doc_dir = obj.get_doc_path()
            files, files_ = [], DocSetFile.query.filter(DocSetFile.docset_id == id).order_by(DocSetFile.no).all()
            to_document = ''
            for file in files_:
                file_full_name = path.join(doc_dir, file.filename)
                files.append({
                    'id': file.id, 
                    'no': file.no, 
                    'name': file.filename, 
                    'dt': datetime.fromtimestamp(path.getctime(file_full_name)).strftime('%d-%m-%Y %H:%M:%S'),
                    'size': size_to_human(path.getsize(file_full_name)),
                })
                #f = open(file_full_name, 'r')
                #to_document += f.read().replace('\r\n', '\n')
                #f.close()
            embeddings = OpenAIEmbeddings()
            vectordb_folder = obj.create_vectordb_name()
            vector_store = Chroma(
                            collection_name=obj.get_collection_name(),
                            embedding_function=embeddings,
                            persist_directory=vectordb_folder,
                        )
            sources = vector_store.get()
            i, documents, metadatas = 0, sources['documents'], sources['metadatas']
            chunks = []
            for document in documents:
                metadata = metadatas[i]
                l = len(document)
                if l >= 160:
                    l = 160
                chunk1, chunk2, chunk3 = document[:int(l / 2)], document[int(l / 2): int(l / -2)], document[int(l / -2):]
                chunks.append({'chunk1': chunk1, 'chunk2': chunk2, 'chunk3': chunk3, 'metadata': metadata})
                i += 1
            chunks.sort(key=lambda x: 10000 * x['metadata']['file_no'] + x['metadata']['chunk_no'])
            return render_chat_template('docset-files.html', form=self, files=files, chunks=chunks)

        # Upload a file to the docset
        if method == 'UPLOAD-FILE':
            obj = DocSet.query.get(id)
            return upload_file(obj)

        # Delete a file from the docset
        if method == 'DELETE-FILE':
            obj = DocSetFile.query.get(id)
            if obj:
                docset = DocSet.query.get(obj.docset_id)
                if docset:
                    embeddings = OpenAIEmbeddings()
                    vectordb_folder = docset.create_vectordb_name()
                    vector_store = Chroma(
                                    collection_name=docset.get_collection_name(),
                                    embedding_function=embeddings,
                                    persist_directory=vectordb_folder,
                                )
                    sources = vector_store.get()
                    i, ids_to_delete = 0, []
                    for vec_id in sources['ids']:
                        if sources['metadatas'][i]['file_no'] == obj.no:
                            ids_to_delete.append(vec_id)
                        i += 1
                    vector_store.delete(ids=ids_to_delete)
                    remove(path.join(docset.get_doc_path(), obj.filename))
                    flash('The file \'' + obj.filename + '\' is deleted.', 'success')
                    DocSetFile.query.filter(DocSetFile.id == obj.id).delete()
                    db.session.commit()
                    flash('The file is deleted.', 'success')
                    return redirect(url_for('docset', id=docset.id))
                flash('Error: The document set is no longer in the database.', 'danger')
                return redirect(url_for('docset', id=obj.docset_id))
            flash('Error: The file is no longer in the database.', 'danger')
            return redirect(url_for('docsets'))

        # Delete the docset
        if method == 'DELETE':
            obj = DocSet.query.get(id)
            # Delete files
            vectordb_folder_path = obj.create_vectordb_name()
            rmtree(path=obj.get_doc_path(), ignore_errors=True)
            rmtree(path=vectordb_folder_path, ignore_errors=True)
            db.session.execute(DocSetFile.__table__.delete().where(DocSetFile.docset_id == id))
            # Delete chatquestions
            db.session.execute(text('DELETE FROM ' + ChatQuestion.__tablename__ + ' WHERE chat_id IN (SELECT id FROM ' + Chat.__tablename__ + ' WHERE docset_id = ' + str(id) + ');'))
            # Delete chats
            db.session.execute(Chat.__table__.delete().where(Chat.docset_id == id))
            # Delete the object
            db.session.delete(obj)
            db.session.commit()
            self.setUserGroupFields()
            flash('The document set has been deleted.', 'info')
            return redirect(url_for('docsets'))

    # See app/forms/usergroup.py for an explanation
    def setUserGroupFields(self):
        # Make sure that the usergroup table has an auth-field for each docset
        docsets = DocSet.query.all()
        usergroup = db.session.execute(text('SELECT * FROM ' + UserGroup.__tablename__ + ';')).keys()
        if len(usergroup) == 0:
            usergroupfields = []
        else:
            usergroupfields = usergroup._keys
        columnnames = []
        # Find fields that do not exsist (and create them)
        for docset in docsets:
            columnname = 'docset_' + str(docset.id)
            columnnames.append(columnname)
            if columnname not in usergroupfields:
                db.session.execute(text('ALTER TABLE ' + UserGroup.__tablename__ + ' ADD COLUMN ' + columnname + ' INTEGER;'))
        # Find fields that should not exists (and delete them)
        for usergroupfield in usergroupfields:
            if usergroupfield[0:7] == 'docset_' and usergroupfield not in columnnames:
                db.session.execute(text('ALTER TABLE ' + UserGroup.__tablename__ + ' DROP COLUMN ' + usergroupfield + ';'))
        db.session.commit()

