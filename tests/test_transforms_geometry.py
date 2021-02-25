import numpy as np
import pdb

from autopilot.transform.geometry import Spheroid, _ellipsoid_func

n_samples = 100

def test_spheroid_init():
    # test that the dang thing initializes as expected with no params
    sphere_1 = Spheroid()
    assert sphere_1._scale is None
    assert sphere_1._offset_source is None
    assert sphere_1._offset_target is None

    # test that when given explicit source that arrays are generated correctly
    sphere_2 = Spheroid(target=(1,2,3,0,1,2),
                        source=(2,4,6,1,3,5))
    assert np.array_equal(sphere_2._scale, np.array((0.5,0.5,0.5)))
    assert np.array_equal(sphere_2._offset_source, np.array((1, 3, 5)))
    assert np.array_equal(sphere_2._offset_target, np.array((0,1,2)))

def test_spheroid_generate_fit():
    for i in range(n_samples):
        # parameterize a target spheroid
        target = ((np.random.rand()+5)*5,
                  (np.random.rand()+5)*5,
                  (np.random.rand()+5)*5,
                  (np.random.rand()-0.5)*20,
                  (np.random.rand()-0.5)*20,
                  (np.random.rand()-0.5)*20)
        # make a spheroid to generate points
        sphere_generator = Spheroid(target=target)

        # test that the generation is good
        noise = np.random.rand()
        max_distance = np.sqrt((noise**2)*3)
        pts = sphere_generator.generate(1000, which="target",noise=noise)
        ellipsoid_fn_out = _ellipsoid_func(pts, *target)
        assert np.all(ellipsoid_fn_out-1 < max_distance)

        # test that fit recovers the target
        sphere_generator.fit(pts, bounds=((0,0,0,-50,-50,-50),(50,50,50,50,50,50)))
        for t_param, fit_param in zip(target, sphere_generator.source):
            assert np.abs(t_param - fit_param) < max_distance

def test_spheroid_process():
    for i in range(n_samples):
        # test that for a known target and source, the target is correctly
        # recovered from points on the source spheroid

        target = ((np.random.rand() + 1) * 10,
                  (np.random.rand() + 1) * 10,
                  (np.random.rand() + 1) * 10,
                  (np.random.rand() - 0.5) * 20,
                  (np.random.rand() - 0.5) * 20,
                  (np.random.rand() - 0.5) * 20)

        source = ((np.random.rand() + 1) * 10,
                  (np.random.rand() + 1) * 10,
                  (np.random.rand() + 1) * 10,
                  (np.random.rand() - 0.5) * 20,
                  (np.random.rand() - 0.5) * 20,
                  (np.random.rand() - 0.5) * 20)

        sphere = Spheroid(target=target, source=source)
        pts = sphere.generate(1000, which="source", noise=0)
        pts_tfm = sphere.process(pts)

        pts_test = _ellipsoid_func(pts, *source)
        pts_tfm_test = _ellipsoid_func(pts_tfm, *target)


        assert np.allclose(pts_test, np.ones(1000))
        assert np.allclose(pts_tfm_test, np.ones(1000))
