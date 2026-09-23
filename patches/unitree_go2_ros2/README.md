# Audited Unitree patch series

Base repository: https://github.com/khaledgabr77/unitree_go2_ros2.git

Base commit: `55ff151632a0220bf3ae0c0772392615d86da7a8`.

Apply only `0001-fix-unitree-application-dependency.patch`. This reproduces the
required local manifest correction found in the Stage 6C reference audit:
`unitree_applications` becomes the actual package name `unitree_application`.
Apply it before rosdep resolution. No robot/controller/camera source is changed.

The reference's other local modification adds a `gui_config` argument to the
upstream `unitree_go2_launch.py`. It is intentionally excluded: the team apartment
entry point includes the existing team simulation launch instead. The separate
front-camera GUI panel is optional presentation, not the RGB publisher or bridge.

The proposed manifest-completeness patch from Stage 6C was a new recommendation,
not an existing required reference modification. It is not included in this
series. Known dependency declaration gaps and explicit prerequisites are recorded
in `docs/DEPENDENCY_SETUP.md` at the project root.

Use the bootstrap helper's `--apply-patches` option. It verifies the pinned HEAD,
origin, and exact working-tree diff; it refuses unrelated edits or hidden index
flags. Repeating it recognizes the already-applied patch. No commit is created.
