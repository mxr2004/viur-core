from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import pytz
import tzlocal

from viur.core import conf, current, db
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.utils import utcNow


class DateBone(BaseBone):
    type = "date"

    def __init__(
        self,
        *,
        creationMagic: bool = False,
        date: bool = True,
        localize: bool = None,
        naive: bool = False,
        time: bool = True,
        updateMagic: bool = False,
        **kwargs
    ):
        """
            Initializes a new DateBone.

            :param creationMagic: Use the current time as value when creating an entity; ignoring this bone if the
                entity gets updated.
            :param updateMagic: Use the current time whenever this entity is saved.
            :param date: Should this bone contain a date-information?
            :param time: Should this bone contain time information?
            :param localize: Assume users timezone for in and output? Only valid if this bone
                                contains date and time-information! Per default, UTC time is used.
            :param naive: Use naive datetime for this bone, the default is aware.
        """
        super().__init__(**kwargs)

        # Either date or time must be set
        if not (date or time):
            raise ValueError("Attempt to create an empty DateBone! Set date or time to True!")

        # Localize-flag only possible with date and time
        if localize and not (date and time):
            raise ValueError("Localization is only possible with date and time!")
        # Default localize all DateBones, if not explicitly defined
        elif localize is None and not naive:
            localize = date and time

        if naive and localize:
            raise ValueError("Localize and naive is not possible!")

        # Magic is only possible in non-multiple bones and why ever only on readonly bones...
        if creationMagic or updateMagic:
            if self.multiple:
                raise ValueError("Cannot be multiple and have a creation/update-magic set!")

            self.readonly = True  # todo: why???

        self.creationMagic = creationMagic
        self.updateMagic = updateMagic
        self.date = date
        self.time = time
        self.localize = localize
        self.naive = naive

    def singleValueFromClient(self, value: str, skel: 'viur.core.skeleton.SkeletonInstance', name: str, origData):
        """
            Reads a value from the client.
            If this value is valid for this bone,
            store this value and return None.
            Otherwise our previous value is
            left unchanged and an error-message
            is returned.

            Value is assumed to be in local time zone only if both self.date and self.time are set to True
            and self.localize is True.

            Value is valid if, when converted into String, it complies following formats:\n
            - is digit (may include one '-') and valid POSIX timestamp: converted from timestamp; assumes UTC timezone\n
            - is digit (may include one '-') and NOT valid POSIX timestamp and not date and time: interpreted as seconds after epoch\n
            - 'now': current time\n
            - 'nowX', where X converted into String is added as seconds to current time\n
            - '%H:%M:%S' if not date and time\n
            - '%M:%S' if not date and time\n
            - '%S' if not date and time\n
            - '%Y-%m-%d %H:%M:%S' (ISO date format)\n
            - '%Y-%m-%d %H:%M' (ISO date format)\n
            - '%Y-%m-%d' (ISO date format)\n
            - '%m/%d/%Y %H:%M:%S' (US date-format)\n
            - '%m/%d/%Y %H:%M' (US date-format)\n
            - '%m/%d/%Y' (US date-format)\n
            - '%d.%m.%Y %H:%M:%S' (EU date-format)\n
            - '%d.%m.%Y %H:%M' (EU date-format)\n
            - '%d.%m.%Y' (EU date-format)\n
            -  \n

            The resulting year must be >= 1900.

            :param name: Our name in the skeleton
            :param value: *User-supplied* request-data, has to be of valid format
            :returns: tuple[datetime or None, [Errors] or None]
        """
        time_zone = self.guessTimeZone()
        rawValue = value
        if str(rawValue).replace("-", "", 1).replace(".", "", 1).isdigit():
            if int(rawValue) < -1 * (2 ** 30) or int(rawValue) > (2 ** 31) - 2:
                value = False  # its invalid
            else:
                value = datetime.fromtimestamp(float(rawValue), tz=time_zone).replace(microsecond=0)
        elif not self.date and self.time:
            try:
                value = datetime.fromisoformat(value)
            except:
                try:
                    if str(rawValue).count(":") > 1:
                        (hour, minute, second) = [int(x.strip()) for x in str(rawValue).split(":")]
                        value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute, second=second,
                                         tzinfo=time_zone)
                    elif str(rawValue).count(":") > 0:
                        (hour, minute) = [int(x.strip()) for x in str(rawValue).split(":")]
                        value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute, tzinfo=time_zone)
                    elif str(rawValue).replace("-", "", 1).isdigit():
                        value = datetime(year=1970, month=1, day=1, second=int(rawValue), tzinfo=time_zone)
                    else:
                        value = False  # its invalid
                except:
                    value = False
        elif str(rawValue).lower().startswith("now"):
            tmpRes = datetime.now(time_zone)
            if len(str(rawValue)) > 4:
                try:
                    tmpRes += timedelta(seconds=int(str(rawValue)[3:]))
                except:
                    pass
            value = tmpRes
        else:
            try:
                value = datetime.fromisoformat(value)
            except:
                try:
                    if " " in rawValue:  # Date with time
                        try:  # Times with seconds
                            if "-" in rawValue:  # ISO Date
                                value = datetime.strptime(str(rawValue), "%Y-%m-%d %H:%M:%S")
                            elif "/" in rawValue:  # Ami Date
                                value = datetime.strptime(str(rawValue), "%m/%d/%Y %H:%M:%S")
                            else:  # European Date
                                value = datetime.strptime(str(rawValue), "%d.%m.%Y %H:%M:%S")
                        except:
                            if "-" in rawValue:  # ISO Date
                                value = datetime.strptime(str(rawValue), "%Y-%m-%d %H:%M")
                            elif "/" in rawValue:  # Ami Date
                                value = datetime.strptime(str(rawValue), "%m/%d/%Y %H:%M")
                            else:  # European Date
                                value = datetime.strptime(str(rawValue), "%d.%m.%Y %H:%M")
                    else:
                        if "-" in rawValue:  # ISO (Date only)
                            value = datetime.strptime(str(rawValue), "%Y-%m-%d")
                        elif "/" in rawValue:  # Ami (Date only)
                            value = datetime.strptime(str(rawValue), "%m/%d/%Y")
                        else:  # European (Date only)
                            value = datetime.strptime(str(rawValue), "%d.%m.%Y")
                except:
                    value = False  # its invalid

        if not value:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")
            ]
        if value.tzinfo and self.naive:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Datetime must be naive")
            ]
        if not value.tzinfo and not self.naive:
            value = time_zone.localize(value)

        value = value.replace(microsecond=0)

        if err := self.isInvalid(value):
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        return value, None

    def isInvalid(self, value):
        """
            Ensure that year is >= 1900
            Otherwise strftime will break later on.
        """
        if isinstance(value, datetime):
            if value.year < 1900:
                return "Year must be >= 1900"

        return super().isInvalid(value)

    def guessTimeZone(self):
        """
        Guess the timezone the user is supposed to be in.
        If not both date and time are set and the localize flag is set, then UTC is used.
        If it cant be guessed, a safe default (UTC) is used
        """
        if self.naive:
            return None
        if not (self.date and self.time and self.localize):
            return pytz.utc

        if conf["viur.instance.is_dev_server"]:
            return tzlocal.get_localzone()

        timeZone = pytz.utc  # Default fallback
        currReqData = current.request_data.get()

        try:
            # Check the local cache first
            if "timeZone" in currReqData:
                return currReqData["timeZone"]
            headers = current.request.get().request.headers
            if "X-Appengine-Country" in headers:
                country = headers["X-Appengine-Country"]
            else:  # Maybe local development Server - no way to guess it here
                return timeZone
            tzList = pytz.country_timezones[country]
        except:  # Non-User generated request (deferred call; task queue etc), or no pytz
            return timeZone
        if len(tzList) == 1:  # Fine - the country has exactly one timezone
            timeZone = pytz.timezone(tzList[0])
        elif country.lower() == "us":  # Fallback for the US
            timeZone = pytz.timezone("EST")
        elif country.lower() == "de":  # For some freaking reason Germany is listed with two timezones
            timeZone = pytz.timezone("Europe/Berlin")
        elif country.lower() == "au":
            timeZone = pytz.timezone("Australia/Canberra")  # Equivalent to NSW/Sydney :)
        else:  # The user is in a Country which has more than one timezone
            pass
        currReqData["timeZone"] = timeZone  # Cache the result
        return timeZone

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        if value:
            # Crop unwanted values to zero
            value = value.replace(microsecond=0)
            if not self.time:
                value = value.replace(hour=0, minute=0, second=0)
            elif not self.date:
                value = value.replace(year=1970, month=1, day=1)
            if self.naive:
                value = value.replace(tzinfo=timezone.utc)
            # We should always deal with timezone aware datetimes
            assert value.tzinfo, "Encountered a naive Datetime object in %s - refusing to save." % name
        return value

    def singleValueUnserialize(self, value):
        if isinstance(value, datetime):
            # Serialized value is timezone aware.
            if self.naive:
                value = value.replace(tzinfo=None)
                return value
            else:
                # If local timezone is needed, set here, else force UTC.
                time_zone = self.guessTimeZone()
                return value.astimezone(time_zone)
        else:
            # We got garbage from the datastore
            return None

    def buildDBFilter(self,
                      name: str,
                      skel: 'viur.core.skeleton.SkeletonInstance',
                      dbFilter: db.Query,
                      rawFilter: Dict,
                      prefix: Optional[str] = None) -> db.Query:
        for key in [x for x in rawFilter.keys() if x.startswith(name)]:
            resDict = {}
            if not self.fromClient(resDict, key, rawFilter):  # Parsing succeeded
                super().buildDBFilter(name, skel, dbFilter, {key: resDict[key]}, prefix=prefix)

        return dbFilter

    def performMagic(self, valuesCache, name, isAdd):
        if (self.creationMagic and isAdd) or self.updateMagic:
            if self.naive:
                valuesCache[name] = utcNow().replace(microsecond=0, tzinfo=None)
            else:
                valuesCache[name] = utcNow().replace(microsecond=0).astimezone(self.guessTimeZone())

    def structure(self) -> dict:
        return super().structure() | {
            "date": self.date,
            "time": self.time,
            "naive": self.naive
        }
