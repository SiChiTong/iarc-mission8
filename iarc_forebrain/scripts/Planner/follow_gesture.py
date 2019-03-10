#!/usr/bin/env python2

import rospy
from sensor_msgs.msg import Image
from geometry_msgs.msg import Point
from std_msgs.msg import Float64
from cv_bridge import CvBridge, CvBridgeError
from tf.transformations import *
import numpy as np
import math
import cv2
import sys
from pointing_detection import pointing_detection
from mode import Mode
from move import Move
from Drone import Drone

SAMPLE_PERIOD = .1
CAM_PITCH = math.pi/2

class FollowGesture(Mode):

    def __init__(self, drone):
        self.bridge = CvBridge()
        self.pub = rospy.Publisher("/gesture_direction", Float64, queue_size=10)
        self.drone = drone
        self.prevTime = rospy.Time.now()
        self.distance = 0
        self.move = None
        self.detected = False
        rate = rospy.Rate(1) # 1 Hz
        rate.sleep()
        rospy.Subscriber("/ardrone/front/image_raw", Image, self.image_raw_callback)

    def image_raw_callback(self, msg):
    	if self.detected or not self.is_active():
    		return
        try:
            if((rospy.Time.now()-self.prevTime).to_sec()<SAMPLE_PERIOD):
                return
            self.prevTime = rospy.Time.now()
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            pos = self.drone.get_pos("odom")
            o = pos.pose.orientation
            orientation = euler_from_quaternion([o.x, o.y, o.z, o.w])
            direction, helmet = pointing_detection(frame, -orientation[1]+CAM_PITCH, pos.pose.position.z, True)
            if direction is None:
                return
            self.pub.publish(direction)
            self.move = Move(self.drone, direction+orientation[2]-math.pi/2)
            self.move.enable(self.distance)
            self.detected = True
            key = cv2.waitKey(1)

        except CvBridgeError as e:
            print(e)

    def enable(self, distance='0', units='meters'):
        self.distance = self.parse(distance, units)
        self.active = True
        self.detected = False
        print('FOLLOW GESTURE: dist = ' + str(self.distance))

    def update(self):
        if self.detected:
            self.move.update()

# Start the node
if __name__ == '__main__':
    f = FollowGesture(Drone())
    f.test()
