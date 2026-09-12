from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from revenue import views

router = DefaultRouter()
router.register("buildings", views.BuildingViewSet)
router.register("units", views.UnitViewSet)
router.register("contracts", views.ContractViewSet)
router.register("rules", views.RuleViewSet)
router.register("versions", views.VersionViewSet)
router.register("details", views.DetailViewSet)
router.register("adjustments", views.AdjustmentViewSet)

urlpatterns = [path("api/", include(router.urls))]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
