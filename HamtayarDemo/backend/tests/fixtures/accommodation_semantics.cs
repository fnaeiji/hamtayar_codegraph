using AutoMapper;
using KeramatTrip.Core.Services;
using Yashil.Common.Web.Infrastructure.BaseClasses;
using Yashil.Common.SharedKernel.Logging;
using Yashil.Common.SharedKernel.Permission;
using YashilUserManagement.Core.Services;
namespace KeramatTrip.Web.Areas.KeramatTripAdminApi.Controllers
{
    public partial class AccommodationController : BaseController<Accommodation, int, AccommodationListViewModel, AccommodationEditModel, AccommodationSimpleViewModel>
    {
        private readonly IMapper _mapper;
        private readonly IAccommodationService _accommodationService;
        private readonly IYashilLogger<Accommodation> _logger;
        private readonly IPermissionService _permissionService;
        private readonly IUserPrincipal _userPrincipal;
        private readonly IUserService _userService;
        private readonly IPersonService _personService;
        private readonly IAccommodationContractService _accommodationContractService;
        private readonly IAccommodationTypeService _accommodationTypeService;
        public AccommodationController(IAccommodationService accommodationService,
            IMapper mapper, IYashilLogger<Accommodation> logger,
            IPermissionService permissionService, IUserPrincipal userPrincipal,
            IUserService userService, IPersonService personService,
            IAccommodationContractService accommodationContractService,
            IAccommodationTypeService accommodationTypeService) : base(accommodationService, mapper, logger, permissionService)
        {
            _mapper = mapper;
            _accommodationService = accommodationService;
            _logger = logger;
            _permissionService = permissionService;
            _userPrincipal = userPrincipal;
            _userService = userService;
            _personService = personService;
            _accommodationContractService = accommodationContractService;
            _accommodationTypeService = accommodationTypeService;
        }
        public object HasAnyActiveContract(int accommodationId) => _accommodationService.HasAnyActiveContract(accommodationId);
        public object Mapping() => _mapper.ConfigurationProvider;
    }
}
namespace Yashil.Common.Web.Infrastructure.BaseClasses
{
    public class BaseController<TEntity, TKey, TList, TEdit, TSimple> { }
}
namespace KeramatTrip.Core.Services
{
    public interface IAccommodationService { }
}
