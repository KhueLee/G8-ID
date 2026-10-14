USE [master]
GO
/****** Object:  Database [G8_WCS]    Script Date: 19-Aug-26 5:36:11 PM ******/
CREATE DATABASE [G8_WCS]
GO
IF (1 = FULLTEXTSERVICEPROPERTY('IsFullTextInstalled'))
begin
EXEC [G8_WCS].[dbo].[sp_fulltext_database] @action = 'enable'
end
GO
ALTER DATABASE [G8_WCS] SET ANSI_NULL_DEFAULT OFF 
GO
ALTER DATABASE [G8_WCS] SET ANSI_NULLS OFF 
GO
ALTER DATABASE [G8_WCS] SET ANSI_PADDING OFF 
GO
ALTER DATABASE [G8_WCS] SET ANSI_WARNINGS OFF 
GO
ALTER DATABASE [G8_WCS] SET ARITHABORT OFF 
GO
ALTER DATABASE [G8_WCS] SET AUTO_CLOSE OFF 
GO
ALTER DATABASE [G8_WCS] SET AUTO_SHRINK OFF 
GO
ALTER DATABASE [G8_WCS] SET AUTO_UPDATE_STATISTICS ON 
GO
ALTER DATABASE [G8_WCS] SET CURSOR_CLOSE_ON_COMMIT OFF 
GO
ALTER DATABASE [G8_WCS] SET CURSOR_DEFAULT  GLOBAL 
GO
ALTER DATABASE [G8_WCS] SET CONCAT_NULL_YIELDS_NULL OFF 
GO
ALTER DATABASE [G8_WCS] SET NUMERIC_ROUNDABORT OFF 
GO
ALTER DATABASE [G8_WCS] SET QUOTED_IDENTIFIER OFF 
GO
ALTER DATABASE [G8_WCS] SET RECURSIVE_TRIGGERS OFF 
GO
ALTER DATABASE [G8_WCS] SET  DISABLE_BROKER 
GO
ALTER DATABASE [G8_WCS] SET AUTO_UPDATE_STATISTICS_ASYNC OFF 
GO
ALTER DATABASE [G8_WCS] SET DATE_CORRELATION_OPTIMIZATION OFF 
GO
ALTER DATABASE [G8_WCS] SET TRUSTWORTHY OFF 
GO
ALTER DATABASE [G8_WCS] SET ALLOW_SNAPSHOT_ISOLATION OFF 
GO
ALTER DATABASE [G8_WCS] SET PARAMETERIZATION SIMPLE 
GO
ALTER DATABASE [G8_WCS] SET READ_COMMITTED_SNAPSHOT OFF 
GO
ALTER DATABASE [G8_WCS] SET HONOR_BROKER_PRIORITY OFF 
GO
ALTER DATABASE [G8_WCS] SET RECOVERY SIMPLE 
GO
ALTER DATABASE [G8_WCS] SET  MULTI_USER 
GO
ALTER DATABASE [G8_WCS] SET PAGE_VERIFY CHECKSUM  
GO
ALTER DATABASE [G8_WCS] SET DB_CHAINING OFF 
GO
ALTER DATABASE [G8_WCS] SET FILESTREAM( NON_TRANSACTED_ACCESS = OFF ) 
GO
ALTER DATABASE [G8_WCS] SET TARGET_RECOVERY_TIME = 60 SECONDS 
GO
USE [G8_WCS]
GO
/****** Object:  Table [dbo].[WCS_Pallet_His]    Script Date: 19-Aug-26 5:36:12 PM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[WCS_Pallet_His](
	[Id] [bigint] IDENTITY(1,1) NOT NULL,
	[Pallet_ID] [nvarchar](100) NOT NULL,
	[Location] [nvarchar](50) NULL,
	[Item_Code] [nvarchar](50) NULL,
	[Ctn] [int] NULL,
	[Qty] [int] NULL,
	[Pcs] [int] NULL,
	[Inner_Carton] [int] NULL,
	[Inner_Pallet] [int] NULL,
	[PO_ID] [bigint] NOT NULL,
	[WH_Code] [nvarchar](50) NULL,
	[Line_ID] [nvarchar](50) NULL,
	[Task_ID] [nvarchar](50) NULL,
	[From_System] [nvarchar](100) NULL,
	[CreatedAt] [datetime] NOT NULL,
	[Status] [nvarchar](50) NOT NULL,
	[DoneAt] [datetime] NOT NULL,
	[DoneReason] [nvarchar](50) NOT NULL,
	[Weight_ref] [int] NULL,
	[Item_Name] [nvarchar](255) NULL,
	[PO_Name] [nvarchar](255) NULL,
	[Pallet_Done] [nvarchar](255) NULL,
	[Pallet_Current] [int] NULL,
	[MFG_Date] [nvarchar](255) NULL,
PRIMARY KEY CLUSTERED 
(
	[Id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[WCS_Pallet_Prod]    Script Date: 19-Aug-26 5:36:12 PM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[WCS_Pallet_Prod](
	[Id] [bigint] IDENTITY(1,1) NOT NULL,
	[Pallet_ID] [nvarchar](100) NOT NULL,
	[Location] [nvarchar](50) NULL,
	[Item_Code] [nvarchar](50) NULL,
	[Ctn] [int] NULL,
	[Qty] [int] NULL,
	[Pcs] [int] NULL,
	[Inner_Carton] [int] NULL,
	[Inner_Pallet] [int] NULL,
	[PO_ID] [bigint] NOT NULL,
	[WH_Code] [nvarchar](50) NULL,
	[Line_ID] [nvarchar](50) NULL,
	[Task_ID] [nvarchar](50) NULL,
	[From_System] [nvarchar](100) NULL,
	[CreatedAt] [datetime] NOT NULL,
	[Status] [nvarchar](50) NULL,
	[Weight_ref] [int] NULL,
	[Item_Name] [nvarchar](255) NULL,
	[PO_Name] [nvarchar](255) NULL,
	[Pallet_Done] [nvarchar](255) NULL,
	[Pallet_Current] [int] NULL,
	[MFG_Date] [nvarchar](255) NULL,
 CONSTRAINT [PK_WCS_Pallet_Prod] PRIMARY KEY CLUSTERED 
(
	[Id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[WCS_Parcels_His]    Script Date: 19-Aug-26 5:36:12 PM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[WCS_Parcels_His](
	[Id] [bigint] IDENTITY(1,1) NOT NULL,
	[ParcelCode] [nvarchar](200) NOT NULL,
	[ReceivedCode] [nvarchar](200) NULL,
	[Pallet_ID] [nvarchar](100) NOT NULL,
	[Location] [nvarchar](50) NULL,
	[Status] [nvarchar](50) NULL,
	[Line_ID] [nvarchar](50) NULL,
	[CreatedAt] [datetime] NOT NULL,
	[DoneAt] [datetime] NOT NULL,
	[DoneReason] [nvarchar](50) NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[Id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[WCS_Parcels_Prod]    Script Date: 19-Aug-26 5:36:12 PM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[WCS_Parcels_Prod](
	[Id] [bigint] IDENTITY(1,1) NOT NULL,
	[ParcelCode] [nvarchar](200) NOT NULL,
	[ReceivedCode] [nvarchar](200) NULL,
	[Pallet_ID] [nvarchar](100) NOT NULL,
	[Location] [nvarchar](50) NULL,
	[Status] [nvarchar](50) NULL,
	[Line_ID] [nvarchar](50) NULL,
	[CreatedAt] [datetime] NOT NULL,
 CONSTRAINT [PK_WCS_Parcels_Prod] PRIMARY KEY CLUSTERED 
(
	[Id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[WCS_PLAN_CONFIG_Temp]    Script Date: 19-Aug-26 5:36:12 PM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[WCS_PLAN_CONFIG_Temp](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[Line_ID] [nvarchar](50) NULL,
	[Item_Code] [nvarchar](50) NULL,
	[Inner_Pallet] [nvarchar](50) NULL,
	[Inner_Carton] [nvarchar](50) NULL,
	[TotalParcel] [nvarchar](50) NULL,
	[TotalPallet] [nvarchar](50) NULL,
	[RealtimeParcel] [nvarchar](50) NULL,
	[RealTimePallet] [nvarchar](50) NULL,
	[Ctn] [int] NULL,
	[Position] [nvarchar](254) NULL,
	[Weight_ref] [int] NULL
) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
/****** Object:  Index [IX_WCS_Pallet_Prod_Pallet]    Script Date: 19-Aug-26 5:36:12 PM ******/
CREATE NONCLUSTERED INDEX [IX_WCS_Pallet_Prod_Pallet] ON [dbo].[WCS_Pallet_Prod]
(
	[Pallet_ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
/****** Object:  Index [IX_WCS_Pallet_Prod_PO_Pallet]    Script Date: 19-Aug-26 5:36:12 PM ******/
CREATE NONCLUSTERED INDEX [IX_WCS_Pallet_Prod_PO_Pallet] ON [dbo].[WCS_Pallet_Prod]
(
	[PO_ID] ASC,
	[Pallet_ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
/****** Object:  Index [IX_WCS_Parcels_Prod_Pallet]    Script Date: 19-Aug-26 5:36:12 PM ******/
CREATE NONCLUSTERED INDEX [IX_WCS_Parcels_Prod_Pallet] ON [dbo].[WCS_Parcels_Prod]
(
	[Pallet_ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
/****** Object:  Index [IX_WCS_Parcels_Prod_Pallet_Status]    Script Date: 19-Aug-26 5:36:12 PM ******/
CREATE NONCLUSTERED INDEX [IX_WCS_Parcels_Prod_Pallet_Status] ON [dbo].[WCS_Parcels_Prod]
(
	[Pallet_ID] ASC,
	[Status] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
/****** Object:  Index [UX_WCS_Parcels_Prod_ParcelCode]    Script Date: 19-Aug-26 5:36:12 PM ******/
CREATE UNIQUE NONCLUSTERED INDEX [UX_WCS_Parcels_Prod_ParcelCode] ON [dbo].[WCS_Parcels_Prod]
(
	[ParcelCode] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[WCS_Pallet_His] ADD  DEFAULT (getdate()) FOR [DoneAt]
GO
ALTER TABLE [dbo].[WCS_Pallet_His] ADD  DEFAULT ('NORMAL') FOR [DoneReason]
GO
ALTER TABLE [dbo].[WCS_Pallet_Prod] ADD  CONSTRAINT [DF_WCS_Pallet_Prod_CreatedAt]  DEFAULT (getdate()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[WCS_Parcels_His] ADD  DEFAULT (getdate()) FOR [DoneAt]
GO
ALTER TABLE [dbo].[WCS_Parcels_His] ADD  DEFAULT ('AUTO_DELETE') FOR [DoneReason]
GO
ALTER TABLE [dbo].[WCS_Parcels_Prod] ADD  CONSTRAINT [DF_WCS_Parcels_Prod_CreatedAt]  DEFAULT (getdate()) FOR [CreatedAt]
GO
/****** Object:  Trigger [dbo].[TR_WCS_Pallet_Prod_To_His]    Script Date: 19-Aug-26 5:36:12 PM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

CREATE TRIGGER [dbo].[TR_WCS_Pallet_Prod_To_His]
ON [dbo].[WCS_Pallet_Prod]
AFTER DELETE
AS
BEGIN
    SET NOCOUNT ON;

    /*
        Trigger tự động copy pallet
        từ bảng PROD sang bảng HIS
        khi pallet bị DELETE.

        Chỉ log những pallet có Status = DONE.
    */

    INSERT INTO dbo.WCS_Pallet_His
    (
        Pallet_ID,
        Location,
        Item_Code,
        Ctn,
        Qty,
        Pcs,
        Inner_Carton,
        Inner_Pallet,
        PO_ID,
        WH_Code,
        Line_ID,
        Task_ID,
        From_System,
        CreatedAt,
        Status,
        Weight_ref,
        Item_Name,
        DoneAt,
        PO_Name,
		Pallet_Current,
		Pallet_Done,
		MFG_Date
    )
    SELECT
        d.Pallet_ID,
        d.Location,
        d.Item_Code,
        d.Ctn,
        d.Qty,
        d.Pcs,
        d.Inner_Carton,
        d.Inner_Pallet,
        d.PO_ID,
        d.WH_Code,
        d.Line_ID,
        d.Task_ID,
        d.From_System,
        d.CreatedAt,
        d.Status,
        d.Weight_ref,
        d.Item_Name,
        GETDATE() AS DoneAt,
        d.PO_Name,
		Pallet_Current,
		Pallet_Done,
		MFG_Date
    FROM deleted d;
END
GO
ALTER TABLE [dbo].[WCS_Pallet_Prod] ENABLE TRIGGER [TR_WCS_Pallet_Prod_To_His]
GO
/****** Object:  Trigger [dbo].[TR_WCS_Parcels_Prod_To_His]    Script Date: 19-Aug-26 5:36:13 PM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TRIGGER [dbo].[TR_WCS_Parcels_Prod_To_His]
ON [dbo].[WCS_Parcels_Prod]
AFTER DELETE
AS
BEGIN
    SET NOCOUNT ON;

    /*
        Trigger tự động lưu lịch sử parcel
        khi parcel bị DELETE khỏi bảng PROD
    */

    INSERT INTO dbo.WCS_Parcels_His
    (
        ParcelCode,
        ReceivedCode,
        Pallet_ID,
        Location,
        Status,
        Line_ID,
        CreatedAt,
        DoneAt,
        DoneReason
    )
    SELECT
        d.ParcelCode,
        d.ReceivedCode,
        d.Pallet_ID,
        d.Location,
        d.Status,
        d.Line_ID,
        d.CreatedAt,
        GETDATE()      AS DoneAt,
        'AUTO_DELETE'  AS DoneReason
    FROM deleted d;
END
GO
ALTER TABLE [dbo].[WCS_Parcels_Prod] ENABLE TRIGGER [TR_WCS_Parcels_Prod_To_His]
GO
USE [master]
GO
ALTER DATABASE [G8_WCS] SET  READ_WRITE 
GO
