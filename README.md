# Photo Tools

Script and tools for working with digital photographs

## Print scans 

I've been scanning envelopes of family photograph prints, mostly from
the 1990s. I put each envelope's photos in a folder with an estimated
date and a subject like "1997-12-25-Christmas". This is the primary
on-disk representation.

There is a script to update the scanned digital image's metadata with
a date-time, derived from the folder date and a time that maintains
the scanned order of the photographs, and description based on the
non-date portion of the folder name. With the example folder name it
would be "Christmas". This metadata is used to allow for appropriate
display in Apple Photos and in Apple Shared Albums with family. 

There is a special case where two folders share the same date. In this
case the times of day between the two folders need to be offset so
the photos do not get intermixed.
