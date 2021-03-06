#!/usr/bin/env python2

import cv2
import numpy as np
import rospy

"""
Time-based filtering of CV bounding boxes.

This uses several assumptions about the world (e.g. that things usually stay in
about the same place, rather than disappearing or teleporting) to filter noisy
CV-derived bounding boxes.  Its primary application is finding humans, but it will
probably work for other things as well.
"""


def toRosTime(t):
    if type(t) is not rospy.rostime.Time:
        return rospy.Time.from_sec(t)
    else:
        return t


def toRosDuration(t):
    if type(t) is not rospy.rostime.Duration:
        return rospy.Duration.from_sec(t)
    else:
        return t


class Box:
    """
    A box consists of (sides, first_seen, last_seen).
    sides are a 4-list (TODO: Or 4-tuple?) of coords, expressed as
    fractions of the total image size, in the order (upper y, left x, 
    lower y, right x).
    first_ and last_seen are rospy times representing the first and
    last times we've seen that box.
    """

    def __init__(self, sides, first_seen=None, last_seen=None):
        self.sides = sides
        self.first_seen = first_seen
        self.last_seen = last_seen

    def dists(self, other):
        """
        Absolute-value distances between my sides and the sides of the other box.
        """
        # Unfortunately, "other's" is not a valid Python variable name.
        return [abs(mine - others) for (mine, others) in zip(self.sides, other.sides)]

    def num_far_sides(self, other, max_dist):
        return sum([1 if (dist > max_dist) else 0 for dist in self.dists(other)])

    def join(self, other):
        """
      "Joins" two boxes into a sort of super-set kinda.
      """

        def softmax(a, b):  # No, not *that* softmax!
            return 0.9 * max(a, b) + 0.1 * min(a, b)

        def softmin(a, b):
            return 0.9 * min(a, b) + 0.1 * max(a, b)

        return [
            f(a, b)
            for (f, a, b) in zip(
                [softmin, softmin, softmax, softmax], self.sides, other.sides
            )
        ]


class Filter:
    """
    A filter object.  Has internal state.

    Each time the filter is run, it takes in a list of boxes (and a time when
    the boxes were seen), and returns a list of filtered boxes.  Boxes are
    filtered using a couple of assumptions:
    * There are few enough boxes that you can generally tell them apart.
    * Objects usually stay in about the same place, with the same shape;
      motions and appearance / disappearance are relatively rare.
    * Boxes might be smaller than the objects they are trying to see, but
      they usually will not be bigger.  So, the most realistic size is
      approximated by the largest size seen.
    """

    def __init__(self, min_age=0.1, max_age=0.5, max_side_dist=0.2, max_far_sides=2):
        """
        Parameters
        ----------
        min_age : float or rospy.rostime.Time
          If a bbox is younger than this, it gets filtered out.
        max_age : float or rospy.rostime.Time
          If a bbox has not been seen for this long, it gets filtered out.
        max_side_dist : float
          Maximum distance, as a fraction of bbox diagonal size, between old
          side location and new side location, before the bbox is
          considered new, rather than another sighting of an existing bbox.
        max_far_sides : int
          If more than this many sides are more than max_side_dist from their
          old locations, then the bbox is considered new.
        """

        self.min_age = toRosDuration(min_age)
        self.max_age = toRosDuration(max_age)

        self.max_side_dist = max_side_dist
        self.max_far_sides = max_far_sides

        self.boxes = []

    def __call__(self, boxes, now):
        """
        Executes the filter, incorporating new data and returning known boxes.
        """

        now = toRosTime(now)
        boxes = [
            Box(box, first_seen=now, last_seen=now) for box in boxes
        ]  # convert to Box objects

        # Incorporate new boxes.  Yes, this is O(n^2).  TODO: Make this faster if it needs it
        # For each old box, find the new box which is closest, and merge it
        for old in self.boxes:
            close = []
            for (i, new) in enumerate(boxes):
                if old.num_far_sides(new, self.max_side_dist) <= self.max_far_sides:
                    close += [(i, new)]
            if close:
                closest = min(close, key=lambda b: np.sum(np.power(old.dists(b[1]), 2)))
                boxes.pop(closest[0])
                old.sides = old.join(closest[1])
                old.last_seen = closest[1].last_seen
        # Add unmerged new boxes
        self.boxes += boxes

        # Delete old boxes
        self.boxes = [
            box for box in self.boxes if (now - box.last_seen) <= self.max_age
        ]

        # Return valid boxes
        return [
            box.sides
            for box in self.boxes
            if (box.last_seen - box.first_seen) >= self.min_age
        ]

    def clear(self):
        """
        Clears the filter's memory, forgetting all bboxes.
        """
        self.boxes = []
