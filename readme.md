# HPC pipelines from XNAT

Syncing slurm job scheduling with XNAT data

See `misc/query.bash` for xml-based search on date

## Output

```
sink/$MRSESSION
 log/
   hpc-heudicov_yyyymmdd.log
   hpc-fs_yyyymmdd.log
 bids/
   sub-$label/[ses-$x/]{anat,func,...}
 deriv/
   unicort/1.0.0
   freesurfer/8.0.0
   fmriprep/25.0.0_fs-8.0.0
   xcpd/1.0.0_fp-25.0.0_fs-8.0.0
```

## Flow
  - cron checks xnat every x (60s?)
  - if new session compared to last: luanch async check number of scans in session until stable.
    `while sleep 5m ?? OR inside HPC job`
  - launch HPC job(s) with dependencies
    - heudiconv reproin into sink/$MRSESSION/bids/$label/ses-1
    - UNT1 to T1Map? w/ bias correction
    - freesurfer bids (b/c use T2w if exists? need T1w instead of UNI. use bias corrected)
    - fmriprep if functional. reuse freesurfer from above
    - protocol compare
  - push back to XNAT


Ideally using singularity containers and storing version/provanance information
sink/$MRSESSION/deriv/$pipeline/$VERSION/
