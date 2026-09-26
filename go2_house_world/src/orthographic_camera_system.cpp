#include <memory>
#include <string>

#include <gz/common/Event.hh>
#include <gz/common/Console.hh>
#include <gz/math/Matrix4.hh>
#include <gz/plugin/Register.hh>
#include <gz/rendering/Camera.hh>
#include <gz/rendering/RenderEngine.hh>
#include <gz/rendering/RenderingIface.hh>
#include <gz/rendering/Scene.hh>
#include <gz/sim/EventManager.hh>
#include <gz/sim/System.hh>
#include <gz/sim/rendering/Events.hh>
#include <sdf/Element.hh>

namespace go2_house_world
{

class OrthographicCameraSystem final :
    public gz::sim::System,
    public gz::sim::ISystemConfigure
{
public:
  void Configure(const gz::sim::Entity &,
                 const std::shared_ptr<const sdf::Element> &sdf,
                 gz::sim::EntityComponentManager &,
                 gz::sim::EventManager &events) override
  {
    this->sensor_name_ = sdf->Get<std::string>("sensor_name");
    this->view_width_ = sdf->Get<double>("view_width");
    this->view_height_ = sdf->Get<double>("view_height");
    this->connection_ = events.Connect<gz::sim::events::PreRender>(
        [this]() { this->ConfigureCamera(); });
  }

private:
  void ConfigureCamera()
  {
    if (this->configured_)
    {
      return;
    }

    // Rendering objects must only be changed from Gazebo's render thread.
    for (const auto &engine_name : gz::rendering::loadedEngines())
    {
      auto *engine = gz::rendering::engine(engine_name);
      if (!engine || engine->SceneCount() == 0)
      {
        continue;
      }
      auto scene = engine->SceneByIndex(0);
      if (!scene)
      {
        continue;
      }

      for (unsigned int index = 0; index < scene->SensorCount(); ++index)
      {
        auto camera = std::dynamic_pointer_cast<gz::rendering::Camera>(
            scene->SensorByIndex(index));
        if (!camera || camera->Name().find(this->sensor_name_) ==
                           std::string::npos)
        {
          continue;
        }

        const double near_clip = camera->NearClipPlane();
        const double far_clip = camera->FarClipPlane();
        const double depth = far_clip - near_clip;
        if (this->view_width_ <= 0.0 || this->view_height_ <= 0.0 ||
            depth <= 0.0)
        {
          return;
        }

        // A fixed world-space width and height give true parallel projection.
        const gz::math::Matrix4d projection(
            2.0 / this->view_width_, 0, 0, 0,
            0, 2.0 / this->view_height_, 0, 0,
            0, 0, -2.0 / depth, -(far_clip + near_clip) / depth,
            0, 0, 0, 1);
        camera->SetProjectionType(gz::rendering::CPT_ORTHOGRAPHIC);
        camera->SetProjectionMatrix(projection);
        gzmsg << "Configured orthographic camera [" << camera->Name()
              << "] with " << this->view_width_ << " m by "
              << this->view_height_ << " m view" << std::endl;
        this->configured_ = true;
        return;
      }
    }
  }

  std::string sensor_name_;
  double view_width_{0.0};
  double view_height_{0.0};
  bool configured_{false};
  gz::common::ConnectionPtr connection_;
};

}  // namespace go2_house_world

GZ_ADD_PLUGIN(go2_house_world::OrthographicCameraSystem,
              gz::sim::System, gz::sim::ISystemConfigure)
