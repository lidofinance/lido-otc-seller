// SPDX-License-Identifier: MIT
pragma solidity 0.8.15;

import "./TokenSeller.sol";
import "./proxy/OssifiableProxy.sol";

contract Setup {
    /// @dev setup specific constants

    // initial allowed slippage value, in BPS
    uint256 public constant SLIPPAGE = 200; // 2%
    address public constant LIDO_AGENT = 0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c;

    bytes32 private constant DEFAULT_ADMIN_ROLE = 0x00;
    bytes32 private constant ORDER_SETTLE_ROLE = keccak256("ORDER_SETTLE_ROLE");
    bytes32 private constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    enum SetupStatus {
        None,
        Deployed,
        Finilized
    }

    struct DeployState {
        address impl;
        address payable proxy;
    }

    address public _deployer;
    SetupStatus public _status;
    DeployState public _state;

    function _checkStatus(SetupStatus status) private view {
        require(_status == status, "Wrong setup status");
    }

    modifier updateStatus(SetupStatus status) {
        _checkStatus(status);
        _;
        _status = SetupStatus(uint8(status) + 1);
    }

    modifier onlyDeployer() {
        require(msg.sender == _deployer, "Only deployer allowed");
        _;
    }

    constructor(address deployer) {
        require(deployer != address(0));
        _deployer = deployer;
        _deploy();
    }

    function deploy() external onlyDeployer {
        _deploy();
    }

    function finalize() external onlyDeployer {
        _finalize();
    }

    function check() external view returns (bool) {
        return _check();
    }

    function _deploy() internal updateStatus(SetupStatus.None) {
        DeployState memory state;

        state.impl = address(new TokenSeller());

        bytes memory data = abi.encodeWithSignature("initialize(uint256)", SLIPPAGE);
        // set Setup contract as temporary proxy admin
        /// @notice roles for Lido Agent are set during initialize call
        state.proxy = payable(new OssifiableProxy(state.impl, address(this), data));

        TokenSeller proxy = TokenSeller(state.proxy);

        // grant temporary right for test
        proxy.grantRole(ORDER_SETTLE_ROLE, _deployer);
        proxy.grantRole(OPERATOR_ROLE, _deployer);

        _state = state;
    }

    function _finalize() internal updateStatus(SetupStatus.Deployed) {
        DeployState memory state = _state;

        TokenSeller proxy = TokenSeller(state.proxy);

        // remove temporary access rights
        proxy.revokeRole(ORDER_SETTLE_ROLE, _deployer);
        proxy.revokeRole(OPERATOR_ROLE, _deployer);
        proxy.renounceRole(DEFAULT_ADMIN_ROLE, address(this));

        // transfer proxy admin to Lido Agent
        OssifiableProxy(state.proxy).proxy__changeAdmin(LIDO_AGENT);
    }

    function _check() internal view returns (bool) {
        _checkStatus(SetupStatus.Finilized);

        DeployState memory state = _state;
        TokenSeller proxy = TokenSeller(state.proxy);

        // check: Agent is only roles holder
        require(proxy.getRoleMemberCount(DEFAULT_ADMIN_ROLE) == 1);
        require(proxy.getRoleMemberCount(ORDER_SETTLE_ROLE) == 1);
        require(proxy.getRoleMemberCount(OPERATOR_ROLE) == 1);

        require(proxy.getRoleMember(OPERATOR_ROLE, 0) == LIDO_AGENT);
        require(proxy.getRoleMember(ORDER_SETTLE_ROLE, 0) == LIDO_AGENT);

        // check: Agent is proxy admin
        require(OssifiableProxy(state.proxy).proxy__getAdmin() == LIDO_AGENT);

        //check values
        require(proxy.getSlippage() == SLIPPAGE);

        return true;
    }
}
