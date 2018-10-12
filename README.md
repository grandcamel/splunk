Steps to remediate a Splunk search head cluster where knowledge object
replication has failed/stopped working. This will parse every
local.meta file under a hard-coded 2, 3 and 4 subdirectories each
containing an 'etc/' tree of the member server (FIX TO USE COMMAND
LINE ARG TO SPECIFY SUBDIRS). It then "merges" all knowledge
objects/files specified by the local.meta stanzas. This defaults to a
subdir called "merged" which contains an "etc" subdir tree of all
files that need to be updated on the selected captain. You can
overwrite these files and then go to
https://SPLUNKHOST/en-US/debug/refresh on the captain. After that
finishes you can run "splunk resync shcluster-replicated-config" on
every non-captain member of the search head cluster.

First draft, caveat emptor, yada yada

- Grand Camel
