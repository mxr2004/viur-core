# -*- coding: utf-8 -*-
from viur.server.bones.bone import baseBone, getSystemInitialized
from viur.server.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from typing import List
import json


class recordBone(baseBone):
	type = "record"

	def __init__(self, using, format=None, multiple=True, *args, **kwargs):
		super(recordBone, self).__init__(multiple=multiple, *args, **kwargs)

		self.using = using
		self.format = format
		if not format or not multiple:
			NotImplemented("A recordBone must be multiple and must have a format set")

		if getSystemInitialized():
			self._usingSkelCache = using()
		else:
			self._usingSkelCache = None

	def setSystemInitialized(self):
		super(recordBone, self).setSystemInitialized()
		self._usingSkelCache = self.using()

	def _restoreValueFromDatastore(self, val):
		"""
			Restores one of our values from the serialized data read from the datastore

			:param value: Json-Encoded datastore property

			:return: Our Value (with restored usingSkel data)
		"""
		value = json.loads(val)
		assert isinstance(value, dict), "Read something from the datastore thats not a dict: %s" % str(type(value))

		usingSkel = self._usingSkelCache
		usingSkel.setValuesCache({})
		usingSkel.unserialize(value)

		return usingSkel.getValuesCache()

	def unserialize(self, valuesCache, name, expando):
		if name not in expando:
			valuesCache[name] = None
			return True

		val = expando[name]

		if self.multiple:
			valuesCache[name] = []

		if not val:
			return True

		if isinstance(val, list):
			for res in val:
				try:
					valuesCache[name].append(self._restoreValueFromDatastore(res))
				except:
					raise
		else:
			try:
				valuesCache[name].append(self._restoreValueFromDatastore(val))
			except:
				raise

		return True

	def serialize(self, valuesCache, name, entity):
		if not valuesCache[name]:
			entity[name] = None

		else:
			usingSkel = self._usingSkelCache
			res = []

			for val in valuesCache[name]:
				usingSkel.setValuesCache(val)
				res.append(json.dumps(usingSkel.serialize()))

			entity.set(name, res, False)

		return entity

	def fromClient(self, valuesCache, name, data):
		#return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Not yet fixed")]
		if not name in data and not any(x.startswith("%s." % name) for x in data):
			return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, name, "Field not submitted")]

		valuesCache[name] = []
		tmpRes = {}

		clientPrefix = "%s." % name

		for k, v in data.items():
			# print(k, v)

			if k.startswith(clientPrefix) or k == name:
				if k == name:
					k = k.replace(name, "", 1)

				else:
					k = k.replace(clientPrefix, "", 1)

				if "." in k:
					try:
						idx, bname = k.split(".", 1)
						idx = int(idx)
					except ValueError:
						idx = 0

						try:
							bname = k.split(".", 1)
						except ValueError:
							# We got some garbage as input; don't try to parse it
							continue

				else:
					idx = 0
					bname = k

				if not bname:
					continue

				if not idx in tmpRes:
					tmpRes[idx] = {}

				if bname in tmpRes[idx]:
					if isinstance(tmpRes[idx][bname], list):
						tmpRes[idx][bname].append(v)
					else:
						tmpRes[idx][bname] = [tmpRes[idx][bname], v]
				else:
					tmpRes[idx][bname] = v

		tmpList = [tmpRes[k] for k in sorted(tmpRes.keys())]

		errors = []

		for i, r in enumerate(tmpList[:]):
			usingSkel = self._usingSkelCache
			usingSkel.setValuesCache({})

			if not usingSkel.fromClient(r):
				for error in refSkel.errors:
					errors.append(
						ReadFromClientError(error.severity, "%s.%s.%s" % (name, i), error.fieldPath),
											error.errorMessage)
			tmpList[i] = usingSkel.getValuesCache()

		cleanList = []

		for item in tmpList:
			err = self.isInvalid(item)
			if err:
				errors.append(
					ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "%s.%s" % (name, tmpList.index(item)), err)
				)
			else:
				cleanList.append(item)

		valuesCache[name] = tmpList

		if not cleanList:
			errors.append(
				ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No value selected")
			)

		if errors:
			return errors

	def getSearchTags(self, values, key):
		def getValues(res, skel, valuesCache):
			for k, bone in skel.items():
				if bone.searchable:
					for tag in bone.getSearchTags(valuesCache, k):
						if tag not in res:
							res.append(tag)
			return res

		value = values.get(key)
		res = []

		if not value:
			return res

		for val in value:
			res = getValues(res, self._usingSkelCache, val)

		return res

	def getSearchDocumentFields(self, valuesCache, name, prefix=""):
		def getValues(res, skel, valuesCache, searchPrefix):
			for key, bone in skel.items():
				if bone.searchable:
					res.extend(bone.getSearchDocumentFields(valuesCache, key, prefix=searchPrefix))

		value = valuesCache.get(name)
		res = []

		if not value:
			return res

		for idx, val in enumerate(value):
			getValues(res, self._usingSkelCache, val, "%s%s_%s" % (prefix, name, str(idx)))

		return res

	def getReferencedBlobs(self, valuesCache, name):
		def blobsFromSkel(skel, valuesCache):
			blobList = set()
			for key, _bone in skel.items():
				blobList.update(_bone.getReferencedBlobs(valuesCache, key))
			return blobList

		res = set()
		value = valuesCache.get(name)

		if not value:
			return res

		if isinstance(value, list):
			for val in value:
				res.update(blobsFromSkel(self._usingSkelCache, val))

		elif isinstance(value, dict):
			res.update(blobsFromSkel(self._usingSkelCache, value))

		return res

	def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> List[str]:
		"""
			This is intentionally not defined as we don't now how to derive a key from the relskel
			being using (ie. which Fields to include and how).

		"""
		raise NotImplementedError
