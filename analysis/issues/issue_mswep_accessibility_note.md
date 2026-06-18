## Title

Considered MSWEP, but not fit for default toolkit backend due to access and licensing friction

## Body

### Summary

We reviewed MSWEP as possible precipitation source for climate-toolkit. It looks scientifically useful, but not fit for normal toolkit integration or default user workflows at present because access path is too gated and operationally awkward.

This is non-urgent. Purpose is to record that MSWEP was considered and why it was not selected as near-term source backend.

### What was reviewed

- Official MSWEP / GloH2O access page
- Official MSWEP documentation
- `aus-ref-clim-data-nci/MSWEP` repo as possible implementation reference

### Why it is not fit for purpose right now

1. Access is not frictionless.
   - Noncommercial users must request approval manually from GloH2O.
   - After approval, download is via shared Google Drive + `rclone`, not open HTTP/API for normal users.
   - Official API/FTP access appears restricted to commercial users.

2. License adds product risk.
   - Official MSWEP distribution is `CC BY-NC 4.0`.
   - That creates ambiguity / limitation for broader product use and any future commercial or mixed-use deployment.

3. Existing public helper repo is HPC / mirror oriented, not toolkit-ready backend.
   - `aus-ref-clim-data-nci/MSWEP` is mainly shell wrappers around `rclone` and `CDO`.
   - It assumes NCI local storage paths such as `/g/data/...`.
   - It does not provide Python package integration, point extraction workflow, or normal user download path.

4. Operational burden is high.
   - Users would likely need separate approval, Drive setup, `rclone`, local mirroring, and large NetCDF handling before toolkit can even extract point time series.
   - This is opposite of desired low-friction toolkit experience.

### Scientific note

MSWEP may still be valuable as advanced comparison source for precipitation benchmarking, especially if users already maintain a local mirror. It appears more promising scientifically than TAMSAT, but much less accessible than preferred toolkit defaults.

### Suggested stance

- Do not implement MSWEP as default backend.
- Do not recommend it for standard user workflows.
- Keep it as possible future `advanced/local-mirror` backend only.
- If revisited, prefer design like `mswep_local`:
  - user already has approved access
  - user already mirrored files locally
  - toolkit only handles point extraction / harmonization

### Current preferred default remains

- `chirps_v3_daily_rnl + agera_5`

### References

- Official MSWEP page: <https://www.gloh2o.org/mswep/>
- Official MSWEP docs: <https://www.gloh2o.org/data/GloH2O_MSWEP_Documentation.pdf>
- Reviewed repo: <https://github.com/aus-ref-clim-data-nci/MSWEP>
