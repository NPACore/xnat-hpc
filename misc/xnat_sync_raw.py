#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pyxnat",
#     "nibabel",
#     "pandas",
# ]
# ///
"""
XNAT uploads downloaded and unzipped to match mace2/scan_data [0]

    {YYYY.MM.DD-HH.MM.SS}/{ID}/{desc}_{yfov}x{xfov}.{seqnum} 

Skips when timestamp session folder exists.

Environment:
  PROJCODE=WPC-8992         # xnat:mrSessionData/PROJECT and DICOM StudyDescription

  RAWROOT="/path/to/sync"   # root where session folders like YYYY.MM.DD-HH.MM.SS/ will be created
                            # will skip download when session folder exist

  DRYRUN=1                  # see but dont download or extract

  FORCED_ACQ='12039|11751'  # subset query to what matches
                            # is re.search on save path like '2025.04.03-09.28.11/12111'

Config:

  Generate a config file using the 'xnat' interface

    from pyxnat import Interface
    xnat = Interface(server=...)
    xnat.save_config('mrrc-xnat.cfg')

  Or make by hand. File is a single line JSON like

    {"server": "https://xnat.mrrc.upmc.edu", "user": "MYUSER", "password": "MYPASSWORD"}




[0] DICOM from PACS written to file & path template from customized storescp(?)
    https://support.dcmtk.org/docs/storescp.html

-----

2026-09-28 - copied from Luna SPA study to stand alone.

-----
For posterity, below inspects dicom and xnat information.

What project is SPA? get from header
>>> a = pydicom.dcmread(glob.glob('raw/20*/sub-12102_ses-1stx/PhoenixZIPReport_0x0.99/*')[0]).StudyDescription
'Brain^WPC-8992' # => WPC-8992

# xnat.inspect.structure(); xnat.inspect.datatypes()
>>> xnat.inspect.datatypes('xnat:mrSessionData')
['xnat:mrSessionData/SESSION_ID', 'xnat:mrSessionData/SUBJECT_ID', 'xnat:mrSessionData/SUBJECT_LABEL', 'xnat:mrSessionData/DATE', 'xnat:mrSessionData/VISIT', 'xnat:mrSessionData/INVEST_SEARCH', 'xnat:mrSessionData/INVEST', 'xnat:mrSessionData/TYPE', 'xnat:mrSessionData/OPERATOR_CSV', 'xnat:mrSessionData/SCANNER_CSV', 'xnat:mrSessionData/MARKER_CSV', 'xnat:mrSessionData/STABILIZATION_CSV', 'xnat:mrSessionData/GEN_AGE', 'xnat:mrSessionData/AGE', 'xnat:mrSessionData/DTI_COUNT', 'xnat:mrSessionData/INSERT_DATE', 'xnat:mrSessionData/INSERT_USER', 'xnat:mrSessionData/LAST_MODIFIED', 'xnat:mrSessionData/MR_SCAN_COUNT_AGG', 'xnat:mrSessionData/PROJECT', 'xnat:mrSessionData/SCAN_COUNT_TYPE', 'xnat:mrSessionData/SCAN_COUNT_DESC', 'xnat:mrSessionData/SCAN_COUNT_CLASS', 'xnat:mrSessionData/SCAN_COUNT_L_TYPE', 'xnat:mrSessionData/SCAN_COUNT_L_DESC', 'xnat:mrSessionData/SCAN_COUNT_L_CLASS']
>>> xnat.inspect.datatypes('xnat:mrScanData')
[]



Scan XML field 'xnat:time' is 'xnat:mrSessionData/XNAT_COL_MRSESSIONDATATIME' in xnat API.
Not pulled by default. Need to specify as column within 'select'.
>>> exp =  xnat.select.experiment("MRRC_XNAT_E34458") # "experiment" (session) object
# print(exp) # slow b/c __repr__() does a few queries
>>> s = exp.scans().fetchone() # first scan object
>>> print(inspect.getsource(s.__repr__)) # xnat._server + s._uri + '?format=html'
>>> x = xml.etree.ElementTree.fromstring(exp.get()) # fetch xml from server, put into tree obj
# see all datatypes groupbed by parent type
>>> pprint.pprint({x:xnat.inspect.datatypes(x) for x in xnat.inspect.datatypes() })
"""


import pyxnat
import os
import re
import json
import tempfile
from warnings import warn
from pyxnat import Interface
import zipfile # to capture error

# ## globals. pulled from environemnt
PROJCODE = os.environ.get("PROJCODE")  #: what project to sync
RAWROOT = os.environ.get("RAWROOT")  #: path to root of local sync

# when DRYRUN is not empty, dont create dirs or download zips
DRYRUN = "echo" if os.environ.get("DRYRUN") else ""


def ses_to_dir(ses: pyxnat.core.jsonutil.JsonTable) -> os.PathLike:
    """
    @param ses - XNAT search result for experiment. should have label (participant), date (yyyy-mm-dd), and time (hh:mm:ss)
    @returns path to local store of session directory
    like /Volumes/Hera/Projects/SPA/raw/2025.04.03-09.28.11/12111/
    """
    datetime = ses.get("xnat_col_mrsessiondatatime")
    if not datetime:
        # most missing. not worth warning
        #warn(f"using midnight. time missing in {ses}")
        datetime = "00:00:00"
    ses_dir = os.path.join(
        RAWROOT,
        ses["date"].replace("-", ".")
        + "-"
        + datetime.replace(":", "."),
        ses["label"],
    )
    return ses_dir


def main(ses_pattern=None):
    # alt: ~/.xnatPass;  +loginone@http://central.xnat.org=password
    xnat = Interface(config="mrrc-xnat.cfg")  # TODO: encrypt
    # xnat.save_config('mrrc-xnat.cfg')

    # proj = xnat.select.projects('WPC-8992')
    # if not proj:
    #    raise Exception('Cannot fetch project. XNAT issue?')
    # subjs = proj.subjects().get()
    # subj = subjs[0]
    # all_mr = xnat.array.experiments(project_id=PROJCODE, experiment_type='xnat:mrSessionData')
    cols = [
        "xnat:mrSessionData/LABEL",
        "xnat:mrSessionData/SESSION_ID",  # XNAT specific locator. use to get filesj
        "xnat:mrSessionData/date",
        "xnat:mrSessionData/XNAT_COL_MRSESSIONDATATIME",  # seen as xnat:time in xml
    ]
    all_ses = xnat.select("xnat:mrSessionData", columns=cols).where(
        [("xnat:mrSessionData/PROJECT", "=", PROJCODE)]
    )
    # all_ses[0].dumps_json() #
    # '[{"label": "12111", "session_id": "MRRC_XNAT_E34458", "date": "2025-04-03", "xnat_col_mrsessiondatatime": "09:28:11"}]'

    # before columns
    # all_ses[0].headers()  # dict_keys(['session_id', 'subject_id', 'subject_label', 'date', 'visit', 'invest_search', 'invest', 'type', 'operator_csv', 'scanner_csv', 'marker_csv', 'stabilization_csv', 'gen_age', 'age', 'dti_count', 'insert_date', 'insert_user', 'last_modified', 'mr_scan_count_agg', 'project', 'scan_count_type', 'scan_count_desc', 'scan_count_class', 'scan_count_l_type', 'scan_count_l_desc', 'scan_count_l_class'])

    if len(all_ses) == 0:  # 20260319 len is 73
        raise Exception("Cannot fetch sessions. XNAT issue?")

    # What sessions to pull?
    if ses_pattern:
        # pull expliclty what was asked for
        mia = [ses for ses in all_ses if re.search(ses_pattern, ses_to_dir(ses))]
    else:
        # Find missing sessions.
        # test against the yyyy.mm.dd-hh.mm.ss toplevel session directory b/c label might be crazy
        # '25_03_14-11_40_37-STD-1_3_12_2_1107_5_2_0_18914' instead of '18914'
        mia = [
            ses for ses in all_ses if not os.path.exists(os.path.dirname(ses_to_dir(ses)))
        ]
    for ses in mia:
        ses_dir = ses_to_dir(ses)  # could have captured this when making 'mia'
        exp = xnat.select.experiment(ses["session_id"])
        scans = exp.scans()
        # want to cache so we don't have to query for each. type is acqlabel. only stored at toplevel?!
        # BUT can't seem to get parameters/fov/x and y for filenames. use xnat._exec instead
        #
        # scaninfos = xnat._get_json(exp._uri + '/scans?columns=ID,type,parameters/fov/x,parameters/fov/y')
        # [{'xnat_imagescandata_id': '728030', 'ID': '1', 'type': 'Localizer_CP_pass',
        #   'URI': '/data/experiments/MRRC_XNAT_E35485/scans/1'},...]
        # scaninfos = {x['ID']: x for x in scaninfos}

        for r in scans.resources():
            if r.label() != "DICOM":
                continue
            scan_id = r.parent().id()

            # get scan parameters for this dicom zip
            # using _exec to get parameters/fov/x and y to match 'disk/mace2/scan_data' names
            sinfo_url = f"{exp._uri}/scans/{scan_id}?format=json"
            sinfo = (
                json.loads(xnat._exec(sinfo_url, "GET").decode())
                .get("items", [{}])[0]
                .get("data_fields")
            )
            if not sinfo:
                print(f"ERROR: cannot find scan info for {r._uri }: scan='{scan_id}'")
                continue
            # want {desc}_{yfov}x{xfov}.{num}
            # remove suspect chars (namely <> in derived mprage.100)
            # name with 0 padded series number, mace2/scan_data doesn't pad
            acqname = (
                re.sub("[^-A-Za-z0-9.]+", "_", sinfo.get("series_description"))
                + f"_{sinfo.get('parameters/fov/y')}x{sinfo.get('parameters/fov/x')}"
                + ".%03d" % int(scan_id)
            )

            acqdir = os.path.join(ses_dir, acqname)
            if os.path.exists(acqdir):
                print(
                    f"WARNING: have '{acqdir}'. Very unexpected -- should be skipping if '{ses_dir}' exists"
                )
                continue

            if DRYRUN:
                print(f"DRYRUN: '{acqdir}' for {r}")
                continue

            with tempfile.TemporaryDirectory() as tmpd:
                try:
                    zip = r.get(tmpd)
                except zipfile.BadZipFile as e:
                    print(f"ERROR: {xnat._server +'/' + r._uri} to {acqdir} ({e}); skipping")
                    # should maybe not continue but error out?
                    #
                    continue

                os.makedirs(acqdir, exist_ok=True)
                if re.search('.zip$', zip):
                    os.system(f"{DRYRUN} unzip -d '{acqdir}' '{zip}'")
                # wont see this. pyxnat errors out trying to unzip
                elif re.search('.dcm$', zip):
                    os.system(f"{DRYRUN} cp '{zip}' '{acqdir}'")
                else:
                    raise Exception(f"unknown file. '{zip}' is not .zip nor .dcm")


def check_env():
    "Make sure we have needed settings."
    if not PROJCODE:
        raise Exception("Must define 'PROJCODE' environment variable. like 'export PROJCODE=WPC-1234'")
    if not RAWROOT:
        raise Exception("Must define 'RAWDROOT' environment variable. like 'export RAWROOT=/local/path/to/raw'")
    return True


if __name__ == "__main__":
    check_env()
    main(ses_pattern=os.environ.get("FORCED_ACQ"))
